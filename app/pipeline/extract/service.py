# OfficerPath AI — PDF Engine (Phase 1, M4)
# Extraction service — orchestrates the ported Dart parser.
#
# Format order (Dart, format_registry.dart): table first, then block
# -> one-liner -> q-only -> flashcard. The paper-identity gate is
# enforced throughout: never merge questions across documents (one
# call = one document).
#
# D15: a separately attached key is NOT in M4 (app flow; M5/M6).
# D5: highlight/colour/italic/circle/underline/cross/OMR are explicit
# non-support — never inferred from text.
# D4: handwriting — Dart flag-only rule (OCR tick/bold -> unverified,
# confidence 0.54). No separation.
# D17: bold markers come from digital block ``style["bold_lines"]``
# (per-line bold, added to the digital extractor in M4). For OCR
# pages bold is UNAVAILABLE — never approximated from text.

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.pipeline.extract.blocks import (
    apply_candidate_scoring,
    compute_number_duplicates,
    compute_number_gaps,
    demote_decoded_numbers,
    interpolate_numbers,
    parse_one_liner,
    parse_standard_block,
    split_into_blocks,
)
from app.pipeline.extract.keys import (
    CHAPTER_HEADING_RE,
    MONTH_HEADING_RE,
    PAPER_HEADING_RE,
    PAPER_REF_RE,
    decide_key_match,
    is_answer_key_heading,
    is_key_only_line,
    is_unknown_key_token,
    key_heading_remainder,
    orphan_adoption_eligible,
    parse_key_entries,
    resolve_answer_token,
)
from app.pipeline.extract.markers import (
    BOLD_MARKER,
    EXPLANATION_HEADING_RE,
    NOTE_RE,
    PAGE_FOOTER_RE,
    clean_stored,
    is_noise_line,
    is_numeric_option_run,
)
from app.pipeline.extract.models import (
    ExtractedQuestion,
    ParseResult,
    PendingQuestion,
    QAPair,
)
from app.pipeline.extract.numbers import (
    is_misread_number_start,
    question_number_detailed,
)
from app.pipeline.extract.qa import scan_flashcards
from app.pipeline.extract.signals import (
    VERIFIED_SOURCES,
    apply_ocr_provenance,
    confidence_for_source,
    verification_status,
)
from app.pipeline.extract.tables import (
    match_pdfplumber_rows_to_lines,
    parse_pipe_delimiter_lines,
    parse_sr_delimiter_lines,
    parse_sr_pdfplumber_tables,
    parse_table_columns,
    parse_table_rows_grid,
)
from app.pipeline.interfaces import OCRBlock

DEFAULT_PAPER_LABEL = "Paper 1"

#: Dart Subject labels (exam.dart:11-31). D14: unknown labels are
#: flagged as ``"unknown"`` — deliberately NOT silently mapped to GK
#: (the Dart wart).
KNOWN_SUBJECT_LABELS: dict[str, str] = {
    "general knowledge": "General Knowledge",
    "pakistan studies": "Pakistan Studies",
    "pak studies": "Pakistan Studies",
    "islamiat": "Islamiat",
    "islamic studies": "Islamiat",
    "current affairs": "Current Affairs",
    "english": "English",
    "everyday science": "Everyday Science",
    "maths & computer": "Maths & Computer",
    "maths and computer": "Maths & Computer",
    "mathematics": "Maths & Computer",
    "computer": "Maths & Computer",
}


@dataclass
class PageLines:
    """One page of input lines for the extractor."""

    page_number: int
    lines: list[str] = field(default_factory=list)
    blocks: list[OCRBlock] | None = None
    tables: list | None = None  # pdfplumber table rows, if available
    is_ocr: bool = False


def _apply_bold_markers(blocks: list[OCRBlock]) -> list[str]:
    """D17: append U+E000 at the end of each bold line's text (the
    Dart marker contract: the marker is consumed by the parser,
    never stored). Per-line bold comes from the digital extractor's
    ``style["bold_lines"]``. OCR blocks carry no bold info."""
    lines: list[str] = []
    for block in blocks:
        block_lines = block.text.split("\n")
        bold_lines = set()
        if block.style:
            bold_lines = set(block.style.get("bold_lines") or [])
        for i, line in enumerate(block_lines):
            if i in bold_lines:
                line = line + BOLD_MARKER
            lines.append(line)
    return lines


def _pages_to_line_entries(pages: list[PageLines]) -> list[dict]:
    """Flatten pages into global line entries, dropping noise lines
    (spec §3.12, counted) and page furniture (spec §12.1)."""
    entries: list[dict] = []
    noise_filtered = 0
    index = 0
    for page in pages:
        if page.blocks is not None:
            ordered = sorted(
                page.blocks,
                key=lambda b: (b.reading_order if b.reading_order is not None else 10**6),
            )
            raw_lines = _apply_bold_markers(ordered)
        else:
            raw_lines = list(page.lines)
        for raw_pos, raw in enumerate(raw_lines):
            text = raw.strip()
            if not text:
                continue
            if PAGE_FOOTER_RE.search(text) and len(text) < 60:
                noise_filtered += 1
                continue
            if is_noise_line(text) and not is_numeric_option_run(raw_lines, raw_pos):
                noise_filtered += 1
                continue
            entries.append(
                {
                    "index": index,
                    "page": page.page_number,
                    "text": text,
                    "paper": DEFAULT_PAPER_LABEL,
                    "part": "",
                    "is_ocr": page.is_ocr,
                }
            )
            index += 1
    entries.append({"__noise_filtered__": noise_filtered})
    return entries


def _paper_label_from_heading(text: str) -> str | None:
    match = PAPER_HEADING_RE.match(text.strip())
    if match:
        kind = match.group(1).strip().title()
        return f"{kind} {match.group(2).strip()}"
    month = MONTH_HEADING_RE.match(text.strip())
    if month:
        return f"{month.group(1).strip().title()} {month.group(2)}"
    return None


def _segment_lines(
    entries: list[dict],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Spec §5.1-5.3, §6.4-6.5, §3.15. Split lines into segments:
    question segments and key segments, each labelled with a paper.
    A bare key heading belongs to the paper whose questions
    immediately PRECEDE it. Explanation blocks are dropped only when
    a complete question (with options) precedes them
    (``questionHasOptions`` guard). Returns (segments, notes)."""
    from app.pipeline.extract.markers import option_line_match

    segments: list[dict[str, Any]] = []
    notes: list[str] = []
    current: dict[str, Any] = {
        "paper": DEFAULT_PAPER_LABEL,
        "kind": "question",
        "explicit": False,
        "lines": [],
    }
    segments.append(current)
    last_question_paper = DEFAULT_PAPER_LABEL
    in_key = False
    drop_explanation = False
    has_options_in_segment = False

    def new_segment(paper: str, kind: str, explicit: bool) -> dict[str, Any]:
        segment = {"paper": paper, "kind": kind, "explicit": explicit, "lines": []}
        segments.append(segment)
        return segment

    def _starts_question_with_options(pos: int) -> bool:
        """Spec §6.4/§6.10 lookahead (<= 12 lines): a question start
        with options following ends a key section. The option
        lookahead stops at the next heading/question start so a
        LATER question's options can never end the section early."""
        from app.pipeline.extract.blocks import _is_option_line as _opt

        text = entries[pos]["text"].strip()
        if question_number_detailed(text) is None and not is_misread_number_start(text):
            return False
        option_lines = 0
        for nxt in entries[pos + 1 : pos + 13]:
            nxt_text = nxt["text"].strip()
            if (
                question_number_detailed(nxt_text) is not None
                or is_misread_number_start(nxt_text)
                or _paper_label_from_heading(nxt_text) is not None
                or is_answer_key_heading(nxt_text)
            ):
                break
            if _opt(nxt_text):
                option_lines += 1
                if option_lines >= 2:
                    return True
        return False

    for pos, entry in enumerate(entries):
        text = entry["text"].strip()
        if not text:
            continue
        note_match = NOTE_RE.match(text)
        if note_match:
            notes.append(f"Note: {note_match.group(1).strip()}")
            continue
        # Headings end an explanation drop and a key section.
        paper_label = _paper_label_from_heading(text)
        if paper_label is not None or CHAPTER_HEADING_RE.match(text):
            drop_explanation = False
            in_key = False
            if paper_label is not None:
                current = new_segment(paper_label, "question", True)
                last_question_paper = paper_label
                entry = {**entry, "paper": paper_label}
            else:
                entry = {**entry, "part": text}
            has_options_in_segment = False
            current["lines"].append(entry)
            continue
        heading, remainder = key_heading_remainder(text)
        if is_answer_key_heading(text) or remainder is not None:
            # A bare "Key"/"Keys" line (often a wrapped QA word) only
            # opens a key section when key-like content actually
            # follows within 3 lines — otherwise it is ordinary text
            # and a false heading would swallow the rest of the book
            # (a key section with no option-bearing questions after
            # it never ends, §6.4).
            if remainder is None:
                # Strict key-content test: a number followed by a
                # single answer letter ("1. C", "1. (C) text", "1. D
                # 58. B ..."). A bare numbered line ("581. Who ...")
                # is a question, not key content — the loose
                # KEY_ENTRY_START_RE matches it and must not be used
                # here.
                from app.pipeline.extract.numbers import (
                    OCR_NUMBER_TOKEN as _TOKEN,
                )

                _key_content_re = re.compile(
                    r"^(?:Q\s*)?" + _TOKEN + r"\s*[\.\)\:\-,]\s*"
                    r"\(?[A-Ea-e]\)?(?:\s|$)"
                )
                follows = False
                for nxt in entries[pos + 1 : pos + 4]:
                    nxt_text = nxt["text"].strip()
                    if _key_content_re.match(nxt_text) or (is_key_only_line(nxt_text)):
                        follows = True
                        break
                if not follows:
                    current["lines"].append({**entry, "paper": current["paper"]})
                    continue
            drop_explanation = False
            in_key = True
            ref = PAPER_REF_RE.search(text)
            if ref:
                paper = f"{ref.group(1).strip().title()} {ref.group(2).strip()}"
                explicit = True
            else:
                paper = last_question_paper
                explicit = False
            current = new_segment(paper, "key", explicit)
            if remainder is not None:
                current["lines"].append({**entry, "text": remainder})
            continue
        if in_key:
            if _starts_question_with_options(pos):
                in_key = False
                current = new_segment(last_question_paper, "question", False)
                has_options_in_segment = False
                current["lines"].append({**entry, "paper": current["paper"]})
                continue
            current["lines"].append({**entry, "paper": current["paper"]})
            continue
        if is_key_only_line(text):
            # Spec §6.10: key-only lines without a heading, captured
            # for the paper whose questions precede them. A bare
            # "N. L" line is only a key entry when the next line is
            # NOT a plain prose continuation (a stem starting with
            # the article "A" — "50. A" + "Is A Software ..." — is a
            # question, not a key entry).
            next_entry = entries[pos + 1] if pos + 1 < len(entries) else None
            bare_single = bool(
                re.fullmatch(
                    r"(?:Q\s*)?\d+\s*[\.\)\:\-,]\s*\(?[A-Ea-e]\)?\s*",
                    text,
                )
            )
            continues_as_prose = False
            if bare_single and next_entry is not None:
                next_text = next_entry["text"].strip()
                continues_as_prose = bool(
                    next_text
                    and question_number_detailed(next_text) is None
                    and not is_misread_number_start(next_text)
                    and not is_key_only_line(next_text)
                    and _paper_label_from_heading(next_text) is None
                    and not is_answer_key_heading(next_text)
                )
            if continues_as_prose:
                current["lines"].append({**entry, "paper": current["paper"]})
                continue
            if current["kind"] != "key":
                current = new_segment(last_question_paper, "key", False)
                in_key = True
            current["lines"].append({**entry, "paper": current["paper"]})
            continue
        if EXPLANATION_HEADING_RE.match(text):
            if has_options_in_segment:
                drop_explanation = True
            continue
        if drop_explanation:
            if (
                question_number_detailed(text) is not None
                or is_misread_number_start(text)
                or _paper_label_from_heading(text) is not None
            ):
                drop_explanation = False
            else:
                continue
        if option_line_match(text) is not None:
            has_options_in_segment = True
        if current["kind"] == "question":
            last_question_paper = current["paper"]
        current["lines"].append({**entry, "paper": current["paper"]})
    return segments, notes


def _finalise_candidate(
    candidate: dict,
    *,
    source_document_id: str,
    is_ocr: bool,
    paper_identity_extra: dict | None = None,
) -> ExtractedQuestion:
    """Apply confidence / verification / OCR-provenance rules
    (spec §7) and build the output model."""
    source = candidate.get("answer_source", "")
    correct_index = candidate.get("correct_index", -1)
    conflicts = list(candidate.get("conflicts", []))
    verified = source in VERIFIED_SOURCES and correct_index >= 0
    if conflicts:
        # Spec §7.6: a question whose signals conflicted is
        # unverified even if a winner was chosen.
        verified = False
    confidence = confidence_for_source(source, verified)
    provenance = "ocr" if is_ocr else "printed"
    verified, confidence = apply_ocr_provenance(source, verified, confidence, provenance)
    identity: dict = {
        "source_document_id": source_document_id,
        "paper_number": None,
        "paper_title": None,
        "exam": None,
        "year": None,
    }
    paper_label = candidate.get("paper", DEFAULT_PAPER_LABEL)
    number_match = re.search(r"(\d+|[A-Z])\s*$", paper_label)
    if number_match:
        identity["paper_number"] = number_match.group(1)
    identity["paper_title"] = paper_label
    if paper_identity_extra:
        identity.update(paper_identity_extra)
    subject = candidate.get("subject")
    if subject is not None:
        identity["subject"] = subject
    return ExtractedQuestion(
        number=candidate.get("number"),
        text=candidate.get("text", ""),
        options=list(candidate.get("options", [])),
        correct_index=correct_index,
        answer_source=source,
        confidence=round(confidence, 3),
        verified=verified,
        verification_status=verification_status(correct_index, verified, source),
        paper=paper_label,
        page=candidate.get("page", 0),
        part=candidate.get("part", ""),
        format=candidate.get("format", "block"),
        explanation=candidate.get("explanation", ""),
        mark_provenance=provenance,
        paper_identity=identity,
        duplicate=False,
        conflicts=conflicts,
        candidate_confidence=candidate.get("candidate_confidence", 0.0),
        candidate_signals=candidate.get("candidate_signals", {}),
    )


def extract_document(
    pages: list[PageLines],
    source_document_id: str,
    *,
    paper_title: str | None = None,
    exam: str | None = None,
    year: int | None = None,
    pdf_bytes: bytes | None = None,
) -> ParseResult:
    """Run the full extraction over one document (one call = one
    document; the paper-identity gate never merges across
    documents). Format order: table first, then block -> one-liner ->
    q-only -> flashcard."""
    flat = _pages_to_line_entries(pages)
    noise_filtered = 0
    entries: list[dict] = []
    for entry in flat:
        if "__noise_filtered__" in entry:
            noise_filtered = int(entry["__noise_filtered__"])
        else:
            entries.append(entry)
    is_ocr = any(page.is_ocr for page in pages)
    segments, notes = _segment_lines(entries)

    result = ParseResult()
    result.noise_lines_filtered = noise_filtered
    result.notes.extend(notes)

    question_lines: list[dict] = []
    key_segments: list[dict[str, Any]] = []
    for segment in segments:
        if segment["kind"] == "key":
            key_segments.append(segment)
        else:
            question_lines.extend(segment["lines"])
    result.key_sections_found = len(key_segments)

    identity_extra: dict = {}
    if paper_title:
        identity_extra["paper_title"] = paper_title
    if exam:
        identity_extra["exam"] = exam
    if year is not None:
        identity_extra["year"] = year

    consumed: set[int] = set()
    candidates: list[dict] = []
    table_questions: list[dict] = []

    # --- table pass first (§9.7) -----------------------------------
    # The line-based Sr# path runs first: it is the primary route for
    # the TestPoint shape, and pdfplumber (full layout analysis per
    # page) is only a fallback when it finds nothing — running both
    # would duplicate the rows.
    sr_questions, sr_consumed = parse_sr_delimiter_lines(question_lines)
    table_questions.extend(sr_questions)
    consumed |= sr_consumed
    if (
        pdf_bytes is not None
        and not sr_questions
        and any("sr#" in e["text"].lower() for e in question_lines)
    ):
        pdf_rows = parse_sr_pdfplumber_tables(pdf_bytes)
        table_questions.extend(pdf_rows)
        # The fallback rows must consume their lines (§9.7), or the
        # grid/block passes re-parse the same rows as phantoms
        # (TestPoint in M4: 580 grid + 364 block duplicates).
        consumed |= match_pdfplumber_rows_to_lines(pdf_rows, question_lines)
    pipe_questions, pipe_consumed = parse_pipe_delimiter_lines(question_lines)
    table_questions.extend(pipe_questions)
    consumed |= pipe_consumed
    remaining = [e for e in question_lines if e["index"] not in consumed]
    grid_questions, grid_pending, grid_consumed = parse_table_rows_grid(remaining)
    table_questions.extend(grid_questions)
    for prow in grid_pending:
        result.pending.append(
            PendingQuestion(
                text=prow["text"],
                options=list(prow["options"]),
                reason="no-key-entry",
                number=prow.get("number"),
                paper=prow.get("paper", DEFAULT_PAPER_LABEL),
                page=prow.get("page", 0),
            )
        )
        result.format_counts["table"] = result.format_counts.get("table", 0) + 1
    consumed |= {remaining[i]["index"] for i in grid_consumed} if grid_consumed else set()
    remaining = [e for e in question_lines if e["index"] not in consumed]
    col_questions, col_consumed = parse_table_columns(remaining)
    table_questions.extend(col_questions)
    consumed |= {remaining[i]["index"] for i in col_consumed} if col_consumed else set()

    for tq in table_questions:
        tq.setdefault("number_kind", "clean" if tq.get("number") else "numberless")
        tq.setdefault("marker_styles", ["table"] * 4)
        tq.setdefault("option_signals", [])
        tq.setdefault("conflicts", [])
        tq.setdefault("explanation", "")
        candidates.append(tq)
        result.format_counts["table"] = result.format_counts.get("table", 0) + 1

    # --- block pass --------------------------------------------------
    # Skipped/excluded diagnostics are DEFERRED until after the QA
    # pass: a block that fails the standard path may still succeed
    # as a flashcard/q-only item, and must not be counted twice
    # (§10.5: skipped/excluded are for blocks that failed EVERY path).
    deferred_diagnostics: list[tuple[str, set[int], str]] = []
    remaining = [e for e in question_lines if e["index"] not in consumed]
    blocks = split_into_blocks(remaining)
    block_consumed: set[int] = set()
    for block in blocks:
        candidate, skip_reason, exclude_reason = parse_standard_block(block)
        if candidate is not None:
            candidates.append(candidate)
            block_consumed.update(e["index"] for e in block)
            result.format_counts[candidate.get("format", "block")] = (
                result.format_counts.get(candidate.get("format", "block"), 0) + 1
            )
            if candidate.get("five_normalised"):
                result.five_option_normalised += 1
            continue
        if len(block) == 1:
            one_liner = parse_one_liner(block[0])
            if one_liner is not None:
                candidates.append(one_liner)
                block_consumed.update(e["index"] for e in block)
                result.format_counts["one-liner"] = result.format_counts.get("one-liner", 0) + 1
                continue
        first_text = block[0]["text"].strip()
        looks_like_question = (
            question_number_detailed(first_text) is not None
            or is_misread_number_start(first_text)
            or (first_text.endswith(("?", "؟")) and len(first_text) > 8)
        )
        snippet = clean_stored(block[0]["text"][:40])
        block_indices = {e["index"] for e in block}
        if exclude_reason:
            deferred_diagnostics.append(
                (
                    f"{block[0].get('paper', '')} Q{snippet}: {exclude_reason}",
                    block_indices,
                    "excluded",
                )
            )
        elif looks_like_question:
            deferred_diagnostics.append(
                (
                    f"{block[0].get('paper', '')} Q{snippet}: {skip_reason or 'failed every path'}",
                    block_indices,
                    "skipped",
                )
            )
        # Blocks that never looked like a question are dropped
        # silently (§10.5) — except a numbered/bare-numbered
        # question start, which must be skipped with a reason.
    consumed |= block_consumed

    # --- q-only / flashcard pass over unconsumed lines --------------
    remaining = [e for e in question_lines if e["index"] not in consumed]
    # Annotate each remaining line with the most recent question
    # number seen in the question lines (for QA pair numbering).
    last_number: int | None = None
    for entry in question_lines:
        info = question_number_detailed(entry["text"].strip())
        if info is not None:
            last_number = info[0]
        elif re.fullmatch(r"\d+", entry["text"].strip()):
            last_number = int(entry["text"].strip())
        entry["qa_number"] = last_number
    qa_dicts, qa_consumed = scan_flashcards(remaining)
    for pair in qa_dicts:
        pair["number"] = pair.get("number") or pair.get("qa_number")
        result.qa_pairs.append(
            QAPair(
                number=pair.get("number"),
                question=pair["question"],
                answer=pair["answer"],
                page=pair.get("page", 0),
                paper=pair.get("paper", DEFAULT_PAPER_LABEL),
            )
        )
        result.format_counts["flashcard"] = result.format_counts.get("flashcard", 0) + 1
    consumed |= qa_consumed
    # Now record the deferred diagnostics, dropping any whose lines
    # were consumed by the QA pass (they succeeded on a later path).
    for message, indices, kind in deferred_diagnostics:
        if indices & qa_consumed:
            continue
        if kind == "excluded":
            result.excluded.append(message)
        else:
            result.skipped.append(message)

    # --- sequence validation prep (§4.3, §1.13) ---------------------
    demote_decoded_numbers(candidates)
    interpolate_numbers(candidates)
    apply_candidate_scoring(candidates)

    # --- key join (§5.4-5.5, §6.9) ----------------------------------
    key_report: list[str] = []
    entries_by_paper: dict[str, dict[int, str]] = {}
    for segment in key_segments:
        blob = "\n".join(e["text"] for e in segment["lines"])
        key_entries = parse_key_entries(blob)
        if key_entries:
            entries_by_paper.setdefault(segment["paper"], {}).update(key_entries)
    explicit_keys = [s for s in key_segments if s.get("explicit")]
    # Orphan adoption (§5.8).
    if len(explicit_keys) == 1 and entries_by_paper:
        orphan_paper = explicit_keys[0]["paper"]
        orphan_entries = entries_by_paper.get(orphan_paper, {})
        question_papers = {c.get("paper") for c in candidates}
        if orphan_paper not in question_papers and orphan_entries:
            question_numbers = [c["number"] for c in candidates if c.get("number")]
            unique = len(question_numbers) == len(set(question_numbers))
            overlap = (
                sum(1 for n in orphan_entries if n in question_numbers) / len(orphan_entries)
                if orphan_entries
                else 0.0
            )
            single_default = all(
                c.get("paper", DEFAULT_PAPER_LABEL) == DEFAULT_PAPER_LABEL for c in candidates
            )
            if orphan_adoption_eligible(
                explicit_key_count=1,
                key_paper_has_questions=False,
                all_questions_in_one_default_segment=single_default,
                question_numbers_unique=unique,
                overlap_fraction=overlap,
            ):
                entries_by_paper[DEFAULT_PAPER_LABEL] = {
                    **entries_by_paper.get(DEFAULT_PAPER_LABEL, {}),
                    **orphan_entries,
                }
                del entries_by_paper[orphan_paper]
                key_report.append(
                    f"Key '{orphan_paper}' adopted for {DEFAULT_PAPER_LABEL} "
                    f"({overlap:.0%} overlap)."
                )
    applied = 0
    for paper, paper_entries in entries_by_paper.items():
        paper_candidates = [c for c in candidates if c.get("paper") == paper]
        if not paper_candidates:
            # §5.4: an explicit paper with no questions is reported,
            # never silently applied elsewhere.
            key_report.append(
                f"Key '{paper}' mili, lekin is PDF mein {paper} ke sawal nahi — key nahi lagayi."
            )
            for number in sorted(paper_entries):
                result.unmatched_key_entries.append(
                    f"{paper} key entry {number} — no matching question (paper has no questions)"
                )
            continue
        numbers = {c["number"] for c in paper_candidates if c.get("number")}
        coverage = (
            sum(1 for n in paper_entries if n in numbers) / len(paper_entries)
            if paper_entries
            else 0.0
        )
        decision = decide_key_match(
            {
                "source_document_id": source_document_id,
                "paper_number": paper,
                "paper_title": paper,
            },
            {
                "source_document_id": source_document_id,
                "paper_number": paper,
                "paper_title": paper,
            },
            key_is_bare=paper == DEFAULT_PAPER_LABEL,
            single_paper_in_document=len({c.get("paper") for c in candidates}) <= 1,
            exclusive_coverage=coverage >= 0.8,
            position_evidence=True,
        )
        if decision["confidence"] in ("needsReview", "unverified", "mismatch"):
            # §5.5: WITHHELD — removed from the join map, never
            # reported as "unmatched"; the decision reason is
            # reported instead.
            key_report.append(f"Key '{paper}' nahi lagayi — {decision['reason']}.")
            continue
        if decision["confidence"] == "highConfidence":
            key_report.append(
                f"Key '{paper}' HIGH CONFIDENCE se lagi — "
                f"{decision['reason']} Save karne se pehle tasdeeq karein."
            )
        remaining_entries: dict[int, str] = dict(paper_entries)
        for candidate in paper_candidates:
            candidate_number: int | None = candidate.get("number")
            if candidate_number is None or candidate_number not in remaining_entries:
                continue
            token = remaining_entries.pop(candidate_number)
            if is_unknown_key_token(token):
                # §6.8: EXCLUDED, never guessed — still becomes a
                # PendingQuestion with reason unknown-key (when it
                # has exactly 4 options).
                candidate["__exclude_unknown_key__"] = True
                applied += 1
                continue
            resolved = resolve_answer_token(token, candidate.get("options", []))
            if resolved is None:
                result.unmatched_key_entries.append(
                    f"{paper} key entry {candidate_number} — token {token!r} resolves to no option"
                )
                continue
            if candidate.get("correct_index", -1) >= 0 and candidate["correct_index"] != resolved:
                candidate.setdefault("conflicts", []).append(
                    f"answer conflict: key says {chr(65 + resolved)}, "
                    f"{candidate.get('answer_source', '')} says "
                    f"{chr(65 + candidate['correct_index'])} — key wins."
                )
            candidate["correct_index"] = resolved
            candidate["answer_source"] = "key"
            applied += 1
        for number in sorted(remaining_entries):
            result.unmatched_key_entries.append(
                f"{paper} key entry {number} — no matching question"
            )
        if decision["confidence"] == "verified":
            key_report.append(f"Key '{paper}' se {applied} jawab lage.")
    result.key_entries_applied = applied
    result.notes.extend(key_report)

    # --- split answered / pending / excluded (§6.18, §10.5) ---------
    duplicate_pages: dict[int, list[int]] = {}
    for candidate in candidates:
        if candidate.get("number") is not None:
            duplicate_pages.setdefault(candidate["number"], []).append(candidate.get("page", 0))
    for candidate in candidates:
        if candidate.pop("__exclude_unknown_key__", False):
            result.pending.append(
                PendingQuestion(
                    text=candidate.get("text", ""),
                    options=list(candidate.get("options", [])),
                    reason="unknown-key",
                    number=candidate.get("number"),
                    paper=candidate.get("paper", ""),
                    page=candidate.get("page", 0),
                )
            )
            result.excluded.append(
                f"Q{candidate.get('number')}: unknown key token — excluded, never guessed"
            )
            continue
        if candidate.get("correct_index", -1) == -1 and len(candidate.get("options", [])) == 4:
            # Answerless with 4 options -> pending for manual
            # correction, NEVER counted in parsed (§6.18).
            result.pending.append(
                PendingQuestion(
                    text=candidate.get("text", ""),
                    options=list(candidate.get("options", [])),
                    reason="no-key-entry",
                    number=candidate.get("number"),
                    paper=candidate.get("paper", ""),
                    page=candidate.get("page", 0),
                )
            )
            continue
        question = _finalise_candidate(
            candidate,
            source_document_id=source_document_id,
            is_ocr=is_ocr,
            paper_identity_extra=identity_extra,
        )
        question_number: int | None = question.number
        if question_number is not None and len(duplicate_pages.get(question_number, [])) > 1:
            question.duplicate = True
        result.questions.append(question)
        if question.answer_source:
            result.answer_sources[question.answer_source] = (
                result.answer_sources.get(question.answer_source, 0) + 1
            )
        result.conflicts.extend(question.conflicts)

    result.number_gaps = compute_number_gaps(candidates)
    result.number_duplicates = compute_number_duplicates(candidates)
    return result


def extract_from_ocr_blocks(
    blocks: list[OCRBlock],
    source_document_id: str,
    **kwargs: Any,
) -> ParseResult:
    """Extract from OCR blocks grouped by page, in reading order."""
    by_page: dict[int, list[OCRBlock]] = {}
    for block in blocks:
        by_page.setdefault(block.page_number, []).append(block)
    pages = [
        PageLines(page_number=page, blocks=blocks_for_page, is_ocr=True)
        for page, blocks_for_page in sorted(by_page.items())
    ]
    return extract_document(pages, source_document_id, **kwargs)


def extract_from_digital_pdf(
    pdf_bytes: bytes,
    source_document_id: str,
    **kwargs: Any,
) -> ParseResult:
    """Extract from a digital PDF: M3 DigitalExtractor per page +
    pdfplumber tables. Bold lines come from the digital extractor's
    per-line bold (D17)."""
    import fitz

    from app.pipeline.interfaces import PageContext
    from app.pipeline.ocr.digital import DigitalExtractor

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = len(doc)
    doc.close()
    extractor = DigitalExtractor()
    pages: list[PageLines] = []
    for page_number in range(1, page_count + 1):
        context = PageContext(
            document_id=uuid.uuid4(),
            page_number=page_number,
            storage_path="",
            pdf_bytes=pdf_bytes,
        )
        try:
            blocks = extractor.recognize(context)
        except ValueError:
            blocks = []
        pages.append(PageLines(page_number=page_number, blocks=blocks, is_ocr=False))
    return extract_document(pages, source_document_id, pdf_bytes=pdf_bytes, **kwargs)
