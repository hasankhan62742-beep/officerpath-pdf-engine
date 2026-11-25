# OfficerPath AI — PDF Engine (Phase 1, M4)
# Block parser — port of the Dart parser rules, spec §1.9-1.15,
# §2.7-2.10, §4.1-4.4, §6.15-6.18, §10.5.
#
# Sources: mcq_parser.dart:2135-2760, 3470-3973, 4170-4420, 5280-5734.

from __future__ import annotations

import re

from app.pipeline.extract.keys import resolve_answer_token
from app.pipeline.extract.markers import (
    EXPLANATION_HEADING_RE,
    INLINE_MARKER_RE,
    OPTION_E_RE,
    PAGE_FOOTER_RE,
    clean_stored,
    defect_reason,
    is_option_continuation,
    normalise_five_options,
    option_line_match,
    split_option_line,
    strip_answer_tail,
    symbol_option_match,
)
from app.pipeline.extract.numbers import (
    bare_number_at_start,
    is_misread_number_start,
    question_number_detailed,
    strip_question_number_prefix,
)
from app.pipeline.extract.scoring import score_candidate
from app.pipeline.extract.signals import (
    ANSWER_LINE_RE,
    BARE_ANSWER_RE,
    INLINE_ANSWER_RE,
    extract_option_signals,
    final_answer_value_conflict,
    resolve_signals,
)

#: Spec §1.10: option-lookahead windows.
FIRST_OPTION_CLOSE_MAX_LINES = 4
OPTIONS_FOLLOW_MAX_LINES = 8
#: Spec §1.15: max stem continuation lines.
MAX_STEM_CONTINUATIONS = 3
#: Spec §1.14.
SOLUTION_HEADING_RE = re.compile(r"^\s*solution\s*(?:[:\-]\s*(.*))?$", re.IGNORECASE)
FINAL_ANSWER_RE = re.compile(r"^\s*final\s+answers?\s*:\s*(.+)$", re.IGNORECASE)
#: Spec §1.12: a domain/junk line is never a numberless stem.
_DOMAIN_LINE_RE = re.compile(r"^\S+\.(com|pk|org|net|edu)\b", re.IGNORECASE)
#: M4 addition: the Urdu NOA file marks the correct option with a
#: trailing ``(Correct)`` suffix. Dart has no such rule; this is
#: recorded as an M4 addition in the report and treated as an
#: explicit printed answer mark (source ``answer-line``).
CORRECT_MARKER_RE = re.compile(r"\(\s*correct\s*\)\s*$", re.IGNORECASE)


#: A bare option marker on its own line — the option text sits on
#: the NEXT line (Urdu NOA shape: ``a.`` then ``Faiz Ahmad Faiz``).
BARE_MARKER_RE = re.compile(r"^\(?([A-Da-d])[\)\.\:\-]\s*$")


def _is_option_line(text: str) -> bool:
    return (
        option_line_match(text) is not None
        or BARE_MARKER_RE.match(text.strip()) is not None
        or split_option_line(text) is not None
        or symbol_option_match(text) is not None
    )


def _options_follow(lines: list[dict], start: int, limit: int = 8) -> bool:
    """Spec §1.10 (``optionsFollow``): >= 2 option lines within
    ``limit`` lines after ``start``."""
    count = 0
    for entry in lines[start + 1 : start + 1 + limit]:
        if _is_option_line(entry["text"]):
            count += 1
            if count >= 2:
                return True
    return False


def _first_option_close(lines: list[dict], start: int) -> bool:
    """Spec §1.10 (``firstOptionClose``): first option within 4
    lines, at most 2 non-option lines between, and no intervening
    line > 70 chars."""
    for offset in range(1, FIRST_OPTION_CLOSE_MAX_LINES + 1):
        if start + offset >= len(lines):
            return False
        text = lines[start + offset]["text"]
        if len(text) > 70:
            return False
        if _is_option_line(text):
            return offset - 1 <= 2
    return False


def _is_question_start(lines: list[dict], index: int, current: list[dict]) -> bool:
    """Spec §1.9-1.12. Whether ``lines[index]`` starts a new block.
    ``current`` is the block being built (empty = at a boundary)."""
    text = lines[index]["text"].strip()
    if not text:
        return False
    if SOLUTION_HEADING_RE.match(text):
        return False
    if question_number_detailed(text) is not None:
        return True
    if is_misread_number_start(text):
        return True
    if text.endswith(("?", "؟")) and len(text) > 8:
        # §1.11: bare-number question start.
        if bare_number_at_start(text) is not None:
            return True
        # §1.10: unnumbered question start — only when the current
        # block is not an unfinished question.
        if current:
            has_options = any(_is_option_line(e["text"]) for e in current)
            first_text = current[0]["text"].strip()
            first_is_start = (
                question_number_detailed(first_text) is not None
                or is_misread_number_start(first_text)
                or (
                    first_text.endswith(("?", "؟")) and bare_number_at_start(first_text) is not None
                )
            )
            if not has_options and first_is_start:
                return False
        if _first_option_close(lines, index) and _options_follow(lines, index):
            return True
    # §1.12: numberless stems — a plausible stem start after a
    # finished question. Answer lines, final-answer lines,
    # explanations and subject lines are NEVER stem candidates
    # (they belong to the previous block — without this exclusion a
    # "Correct Answer:" line splits, because the NEXT question's
    # options follow within 8 lines).
    if current and any(_is_option_line(e["text"]) for e in current):
        # A block ending in a bare marker ("a." with its text on the
        # next line) is unfinished — the next line is that marker's
        # option text, never a new stem.
        if BARE_MARKER_RE.match(current[-1]["text"].strip()):
            return False
        if (
            ANSWER_LINE_RE.match(text)
            or BARE_ANSWER_RE.match(text)
            or FINAL_ANSWER_RE.match(text)
            or EXPLANATION_HEADING_RE.match(text)
            or OPTION_E_RE.match(text)
            or text.lower().startswith("subject:")
        ):
            return False
        words = text.split()
        if (
            len(words) > 1
            and not text[0].isdigit()
            and len(text) <= 120
            and not _DOMAIN_LINE_RE.match(text)
            and not _is_option_line(text)
            and _options_follow(lines, index)
        ):
            return True
    return False


def split_into_blocks(lines: list[dict]) -> list[list[dict]]:
    """Spec §1.9-1.15 block splitting. Solution blocks (``Solution:``
    ... ``Final Answer:``) never split on their numbered working
    steps."""
    blocks: list[list[dict]] = []
    current: list[dict] = []
    in_solution = False
    for i, entry in enumerate(lines):
        text = entry["text"].strip()
        if SOLUTION_HEADING_RE.match(text):
            in_solution = True
        if in_solution and FINAL_ANSWER_RE.match(text):
            in_solution = False
        if current and not in_solution and _is_question_start(lines, i, current):
            blocks.append(current)
            current = [entry]
        else:
            current.append(entry)
    if current:
        blocks.append(current)
    return blocks


def _collect_stem(block: list[dict], start: int) -> tuple[str, int, list[str]]:
    """Spec §1.15 (``_splitQuestionAndRest``). Question text = first
    line (prefix stripped) + continuation lines: plain lines after
    it, before the first option/answer/explanation/subject line, at
    most 3, stopping after a line ending in ``?``/``؟``. Returns
    (stem, next_index, explanation_lines)."""
    first = block[start]
    stem = strip_question_number_prefix(first["text"].strip())
    stem = strip_answer_tail(stem)
    parts = [stem] if stem else []
    explanations: list[str] = []
    i = start + 1
    continuations = 0
    while i < len(block) and continuations < MAX_STEM_CONTINUATIONS:
        text = block[i]["text"].strip()
        if (
            not text
            or _is_option_line(text)
            or ANSWER_LINE_RE.match(text)
            or BARE_ANSWER_RE.match(text)
            or EXPLANATION_HEADING_RE.match(text)
            or text.lower().startswith("subject:")
        ):
            break
        parts.append(text)
        continuations += 1
        i += 1
        if text.endswith(("?", "؟")):
            break
    return " ".join(parts).strip(), i, explanations


def parse_one_liner(entry: dict) -> dict | None:
    """Spec §2.4/§6.17 (``_parseOneLiner``). Q + all 4 options on one
    line, markers ``(a)``-``(d)`` / ``A.`` / ``1)`` / ``(i)``. Requires
    a complete consecutive sequence ``a,b,c,d`` or ``1,2,3,4`` or
    ``i,ii,iii,iv`` (checked as a 4-window over the marker matches)
    AND real question words (>= 3 chars) before the first marker —
    so a compact key line ``1. A 2. B 3. C 4. D`` is not a one-liner.
    Answer on the same line after the last option, or on the next
    line."""
    text = entry["text"]
    matches = list(INLINE_MARKER_RE.finditer(text))
    if len(matches) < 4:
        return None
    for window_start in range(len(matches) - 3):
        window = matches[window_start : window_start + 4]
        tokens = [m.group(1).lower() for m in window]
        if tokens in (
            ["a", "b", "c", "d"],
            ["1", "2", "3", "4"],
            ["i", "ii", "iii", "iv"],
        ):
            before = text[: window[0].start()].strip()
            number_info = question_number_detailed(before)
            before = strip_question_number_prefix(before)
            before = strip_answer_tail(before)
            words = [w for w in re.split(r"\s+", before) if len(w) >= 3]
            if not words:
                continue
            options: list[str] = []
            for k, match in enumerate(window):
                end = window[k + 1].start() if k + 1 < 4 else len(text)
                option_text = text[match.end() : end].strip(" \t,;")
                # Cut a trailing answer tail from the last option.
                if k == 3:
                    tail = INLINE_ANSWER_RE.search(option_text)
                    if tail:
                        option_text = option_text[: tail.start()].strip()
                options.append(clean_stored(option_text))
            if any(not opt for opt in options):
                continue
            number = number_info[0] if number_info else None
            return {
                "number": number,
                "number_kind": ("decoded" if number_info and number_info[1] else "clean")
                if number_info
                else "numberless",
                "text": clean_stored(before),
                "options": options,
                "correct_index": -1,
                "answer_source": "",
                "page": entry["page"],
                "paper": entry.get("paper", "Paper 1"),
                "format": "one-liner",
                "marker_styles": ["inline"] * 4,
                "option_signals": [
                    {"bold": False, "tick": False, "asterisk": False} for _ in range(4)
                ],
            }
    return None


def parse_standard_block(block: list[dict]) -> tuple[dict | None, str | None, str | None]:
    """Parse one standard block. Returns (candidate, skip_reason,
    exclude_reason) — exactly one of the three is non-None.
    Spec §10.5: a block that looked like a question but failed every
    path is skipped with a reason; a defective / 3-option / unknown-
    key block is excluded with a reason."""
    if not block:
        return None, None, None
    defect = defect_reason([e["text"] for e in block])
    if defect:
        return None, None, defect
    number_info = question_number_detailed(block[0]["text"].strip())
    number_kind = "numberless"
    number = None
    if number_info is not None:
        number, decoded = number_info
        number_kind = "decoded" if decoded else "clean"
    else:
        bare = bare_number_at_start(block[0]["text"].strip())
        if bare is not None and block[0]["text"].strip().endswith(("?", "؟")):
            number = bare
            number_kind = "bare"
    stem, idx, _explanations = _collect_stem(block, 0)
    options: list[str] = []
    option_signals: list[dict[str, bool]] = []
    marker_styles: list[str] = []
    answer_line_token: str | None = None
    final_answer_value: str | None = None
    explanation_parts: list[str] = []
    in_explanation = False
    i = idx
    while i < len(block):
        text = block[i]["text"]
        stripped = text.strip()
        if EXPLANATION_HEADING_RE.match(stripped):
            in_explanation = True
            i += 1
            continue
        if in_explanation:
            explanation_parts.append(stripped)
            i += 1
            continue
        if not stripped or PAGE_FOOTER_RE.match(stripped):
            i += 1
            continue
        final_match = FINAL_ANSWER_RE.match(stripped)
        if final_match:
            answer_line_token = final_match.group(1)
            value_match = re.match(
                r"^\(?\s*[A-Ea-e]\s*\)?\s*[.\)\:\-]?\s*(.+)$",
                answer_line_token.strip(),
            )
            if value_match and value_match.group(1).strip():
                final_answer_value = value_match.group(1).strip()
            i += 1
            continue
        answer_match = ANSWER_LINE_RE.match(stripped)
        if answer_match and not options:
            # An answer line before any option is a q-only shape, not
            # a standard block answer — leave it for the QA pass.
            i += 1
            continue
        if answer_match:
            answer_line_token = answer_match.group(1)
            i += 1
            continue
        if BARE_ANSWER_RE.match(stripped) and options:
            answer_line_token = stripped
            i += 1
            continue
        # Multi-option line (spec §2.6-2.7).
        split = split_option_line(stripped)
        if split is not None and len(options) + len(split) <= 5:
            # The question tail before the first marker joins the stem
            # when the split opens the set at A.
            if split[0][0] == "A" and not options:
                first_marker = re.search(r"[\(\[]?\s*A\s*[\)\.\:\-]", stripped)
                if first_marker:
                    tail = stripped[: first_marker.start()].strip()
                    if tail:
                        stem = (stem + " " + tail).strip()
            for _letter, opt_text in split:
                options.append(opt_text)
                option_signals.append(extract_option_signals(opt_text))
                marker_styles.append("inline")
            i += 1
            continue
        bare_marker = BARE_MARKER_RE.match(stripped)
        if bare_marker is not None and i + 1 < len(block):
            # Marker-only line: the option text is the next line.
            next_text = block[i + 1]["text"].strip()
            if (
                next_text
                and option_line_match(next_text) is None
                and BARE_MARKER_RE.match(next_text) is None
                and not ANSWER_LINE_RE.match(next_text)
                and len(options) < 5
            ):
                options.append(next_text)
                option_signals.append(extract_option_signals(next_text))
                marker_styles.append(bare_marker.group(0))
                i += 2
                continue
        single = option_line_match(stripped)
        if single is None and len(options) == 4:
            # Spec §2.3: E is opt-in only after A-D are collected.
            e_match = OPTION_E_RE.match(stripped)
            if e_match is not None:
                single = ("E", e_match.group(2))
        if single is None:
            # A1: symbol-marked option ("© 274", "O None Of These").
            # Positional — the 1st symbol option is A, the 2nd B, ...
            symbol_text = symbol_option_match(stripped)
            if symbol_text is not None:
                if len(options) < 5:
                    options.append(symbol_text)
                    option_signals.append(extract_option_signals(symbol_text))
                    marker_styles.append("symbol")
                i += 1
                continue
        if single is not None:
            letter, opt_text = single
            if len(options) >= 5:
                i += 1
                continue
            options.append(opt_text)
            option_signals.append(extract_option_signals(opt_text))
            style_match = re.match(r"^\(?[A-Da-d][\)\.\:\-]", stripped)
            marker_styles.append(style_match.group(0) if style_match else "?")
            i += 1
            continue
        if options and is_option_continuation(options[-1], stripped):
            # Spec §2.8: join, then re-extract signals from the joined
            # text (the tail often carries the ``*`` marker).
            joined = options[-1] + " " + stripped
            options[-1] = joined
            option_signals[-1] = extract_option_signals(joined)
            i += 1
            continue
        if options and len(options) < 4 and not stem.endswith(("?", "؟")):
            # A plain line before the options are complete is a stem
            # continuation the stem collector missed (wrapped stem).
            stem = (stem + " " + stripped).strip()
            i += 1
            continue
        i += 1
    if not options:
        return None, "no options found", None
    if len(options) not in (4, 5):
        # D6: 3-option (or 6+) questions are EXCLUDED with reason,
        # never normalised (Dart defines only 4 and 5->4).
        return (
            None,
            None,
            f"excluded: {len(options)} options (only 4, or 5 normalised to 4, are supported)",
        )
    # M4 addition: trailing "(Correct)" on exactly one option is the
    # Urdu NOA file's printed answer mark.
    correct_marked = [k for k, opt in enumerate(options) if CORRECT_MARKER_RE.search(opt)]
    if len(correct_marked) == 1 and answer_line_token is None:
        answer_line_token = chr(65 + correct_marked[0])
    if len(correct_marked) > 1:
        return None, None, "excluded: multiple (Correct) marks"
    options = [
        clean_stored(re.sub(r"\(\s*correct\s*\)\s*$", "", opt, flags=re.IGNORECASE))
        for opt in options
    ]
    # Strip tick/asterisk/bold markers from stored option text.
    from app.pipeline.extract.signals import clean_option_text

    options = [clean_option_text(opt) for opt in options]
    stem = clean_stored(stem)
    if not stem:
        return None, "empty question stem", None
    # Spec §2.10: 5 -> 4 normalisation needs the answer.
    five_normalised = False
    dropped = ""
    if len(options) == 5:
        resolved = None
        if answer_line_token is not None:
            # A1: the inline answer line states a VALUE ("Correct
            # Answer Is: 1"), so an exact option-text match wins
            # over the bare-number index reading.
            resolved = resolve_answer_token(answer_line_token, options, prefer_text=True)
        if resolved is None:
            return (
                None,
                None,
                "excluded: 5 options with no usable answer (normalising needs the answer)",
            )
        normalised = normalise_five_options(options, resolved)
        if normalised is None:
            return None, None, "excluded: 5-option normalisation failed"
        options, resolved, dropped = normalised
        five_normalised = True
        answer_line_token = chr(65 + resolved) if resolved < 4 else None
    correct_index, source, conflicts = resolve_signals(
        option_signals[: len(options)],
        answer_line_token,
        None,
        options,
        # A1: the inline answer line states a VALUE (see above).
        resolve_token=lambda tok, opts: resolve_answer_token(tok, opts, prefer_text=True),
    )
    if final_answer_value and correct_index >= 0:
        conflict = final_answer_value_conflict(correct_index, final_answer_value, options)
        if conflict:
            conflicts.append(conflict)
    candidate = {
        "number": number,
        "number_kind": number_kind,
        "text": stem,
        "options": options,
        "correct_index": correct_index,
        "answer_source": source,
        "page": block[0]["page"],
        "paper": block[0].get("paper", "Paper 1"),
        "format": "block",
        "explanation": " ".join(explanation_parts).strip(),
        "marker_styles": marker_styles[: len(options)],
        "option_signals": option_signals[: len(options)],
        "five_normalised": five_normalised,
        "dropped": dropped,
        "conflicts": conflicts,
        "answer_line_token": answer_line_token,
    }
    return candidate, None, None


def interpolate_numbers(candidates: list[dict]) -> None:
    """Spec §1.13. A run of numberless OPTION-bearing blocks is
    numbered only when the run length exactly fills the gap between
    its numbered neighbours; a leading run before the first numbered
    block counts back from it (numbering starts at 1); a trailing run
    is left null. Only option-bearing blocks consume a number."""
    # Group consecutive numberless candidates (in reading order).
    i = 0
    while i < len(candidates):
        if candidates[i].get("number") is not None:
            i += 1
            continue
        run_start = i
        while i < len(candidates) and candidates[i].get("number") is None:
            i += 1
        run = candidates[run_start:i]
        if not run:
            continue
        prev_num = candidates[run_start - 1].get("number") if run_start > 0 else None
        next_num = candidates[i].get("number") if i < len(candidates) else None
        if prev_num is not None and next_num is not None:
            gap = next_num - prev_num - 1
            if gap == len(run):
                for k, candidate in enumerate(run):
                    candidate["number"] = prev_num + 1 + k
                    candidate["number_kind"] = "interpolated"
        elif prev_num is None and next_num is not None:
            # Leading run counts back from the first numbered block;
            # numbering starts at 1.
            first = next_num - len(run)
            if first >= 1:
                for k, candidate in enumerate(run):
                    candidate["number"] = first + k
                    candidate["number_kind"] = "interpolated"
        # Trailing run: left null (a new section may restart
        # numbering there).


def demote_decoded_numbers(candidates: list[dict]) -> None:
    """Spec §4.3. A number from an OCR-misread token survives ONLY
    when it fits strictly between the trusted (clean-digit or
    sequence-interpolated) numbers around it in the SAME paper.
    Demote to null when: it duplicates a trusted number, or is not
    strictly after the previous accepted number, or is not strictly
    before the next trusted number. Clean numbers are NEVER demoted.
    Only option-bearing blocks are validated."""
    trusted = [
        c
        for c in candidates
        if c.get("number") is not None
        and c.get("number_kind") in ("clean", "interpolated")
        and len(c.get("options", [])) == 4
    ]
    for candidate in candidates:
        if candidate.get("number_kind") != "decoded":
            continue
        number = candidate.get("number")
        if number is None:
            continue
        paper = candidate.get("paper", "Paper 1")
        same_paper = [c for c in trusted if c.get("paper", "Paper 1") == paper]
        if any(c.get("number") == number for c in same_paper):
            candidate["number"] = None
            candidate["number_kind"] = "demoted"
            continue
        # Strictly-between check against the nearest trusted numbers
        # in reading order.
        idx = candidates.index(candidate)
        prev_trusted = None
        next_trusted = None
        for pos, c in enumerate(candidates):
            if c.get("paper", "Paper 1") != paper:
                continue
            if c.get("number") is None:
                continue
            if c.get("number_kind") not in ("clean", "interpolated"):
                continue
            if pos < idx:
                prev_trusted = c["number"]
            elif pos > idx and next_trusted is None:
                next_trusted = c["number"]
        demote = (prev_trusted is not None and not number > prev_trusted) or (
            next_trusted is not None and not number < next_trusted
        )
        if demote:
            candidate["number"] = None
            candidate["number_kind"] = "demoted"


def compute_number_gaps(candidates: list[dict]) -> list[str]:
    """Spec §4.1. Gaps reported, never filled. From the sorted set of
    parsed numbers; any missing number between the lowest and highest
    is a gap, reported WITH the bounding pages. Empty when fewer than
    2 numbers. Bare-numbered books get NO gap report (§4.4)."""
    numbered = [
        c
        for c in candidates
        if c.get("number") is not None
        and c.get("number_kind") in ("clean", "decoded", "interpolated")
    ]
    numbers = sorted({c["number"] for c in numbered})
    if len(numbers) < 2:
        return []
    page_of: dict[int, int] = {}
    for c in numbered:
        page_of.setdefault(c["number"], c.get("page", 0))
    gaps: list[str] = []
    missing: list[int] = []
    for n in range(numbers[0], numbers[-1] + 1):
        if n not in numbers:
            missing.append(n)
    if not missing:
        return []
    # Group into ranges.
    ranges: list[list[int]] = [[missing[0]]]
    for n in missing[1:]:
        if n == ranges[-1][-1] + 1:
            ranges[-1].append(n)
        else:
            ranges.append([n])
    for group in ranges:
        first, last = group[0], group[-1]
        before = max(n for n in numbers if n < first)
        after = min(n for n in numbers if n > last)
        if len(group) == 1:
            gaps.append(
                f"Q{first} missing between Q{before} (page "
                f"{page_of.get(before, 0)}) and Q{after} (page "
                f"{page_of.get(after, 0)})"
            )
        else:
            gaps.append(
                f"Q{first}–Q{last} missing between Q{before} (page "
                f"{page_of.get(before, 0)}) and Q{after} (page "
                f"{page_of.get(after, 0)}) ({len(group)} questions missing)"
            )
    return gaps


def compute_number_duplicates(candidates: list[dict]) -> list[str]:
    """Spec §4.2. Duplicates reported, never merged. ``Q8 appears
    twice (page 1, page 2)``. Both copies are kept as parsed."""
    pages: dict[int, list[int]] = {}
    for c in candidates:
        if c.get("number") is not None:
            pages.setdefault(c["number"], []).append(c.get("page", 0))
    duplicates: list[str] = []
    for number in sorted(pages):
        if len(pages[number]) > 1:
            page_list = ", ".join(f"page {p}" for p in pages[number])
            duplicates.append(f"Q{number} appears {len(pages[number])} times ({page_list})")
    return duplicates


def apply_candidate_scoring(candidates: list[dict], *, column_consistent: bool = True) -> None:
    """Attach ``candidate_confidence`` + ``candidate_signals`` to
    every candidate (M4 addition — evidence only, never overrides a
    rule). Position continuity: a candidate is continuous when its
    number follows the previous candidate's number (or it is the
    first candidate)."""
    previous_number: int | None = None
    for candidate in candidates:
        number = candidate.get("number")
        if candidate.get("number_kind") == "clean":
            number_kind = "clean"
        elif candidate.get("number_kind") == "decoded":
            number_kind = "decoded"
        elif candidate.get("number_kind") in ("interpolated", "bare"):
            number_kind = "numberless"
        else:
            number_kind = "none" if number is None else "numberless"
        continuous = True
        if previous_number is not None and number is not None:
            continuous = number == previous_number + 1
        confidence, signals = score_candidate(
            number_kind=number_kind,
            n_options=len(candidate.get("options", [])),
            marker_styles=candidate.get("marker_styles", []),
            position_continuous=continuous,
            column_consistent=column_consistent,
        )
        candidate["candidate_confidence"] = confidence
        candidate["candidate_signals"] = signals
        if number is not None:
            previous_number = number
