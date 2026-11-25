# OfficerPath AI — PDF Engine (Phase 1, M6)
# Matching service: join M4 extraction + M5 answer resolution into
# resolved MCQs, promote answerable pending questions (ADR-007),
# validate, and report. Also the in-process document parse used by
# the review/parse API (POST /api/v1/documents/parse): digital text
# layer first, else per-page Tesseract OCR with per-page PSM
# selection, layout, extraction, key-region-located key detection,
# resolution, promotion, matching, validation.
#
# Pipeline order (load-bearing):
#   extract -> key-region-located key detection -> resolve ->
#   apply_resolution (writes onto questions) -> promote_pending
#   (moves answerable pendings to questions) -> match_document
#   (builds ResolvedMCQ + validates + reports).
# Promotion uses the RAW (pre-calibration) confidence; calibration
# is applied only when a fitted calibration is supplied to
# match_document.

from __future__ import annotations

import json
import uuid
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from app.config import Settings
from app.pipeline.answers.models import ResolvedAnswer
from app.pipeline.answers.service import (
    AnswerResolution,
    apply_resolution,
    resolve_document_answers,
)
from app.pipeline.extract.models import ExtractedQuestion, ParseResult
from app.pipeline.matching import calibration as calibration_mod
from app.pipeline.matching.key_region import parse_key_entries_in_region
from app.pipeline.matching.models import MatchedDocument, ResolvedMCQ
from app.pipeline.matching.promotion import PromotionReport, promote_pending
from app.pipeline.matching.report import build_document_report
from app.pipeline.matching.validate import validate_matched_document

if TYPE_CHECKING:
    from app.pipeline.layout.analyzer import GeometryLayoutAnalyzer
    from app.pipeline.pdf.quality import PageQuality

#: Fitted calibration written by scripts/benchmark_m6.py; the parse
#: endpoint loads it when present so served confidences are
#: calibrated. Absent file = raw confidences, reported as such.
CALIBRATION_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "docs"
    / "benchmarks"
    / "m6-calibration.json"
)


def load_calibration() -> calibration_mod.Calibration | None:
    """Load the fitted calibration from the benchmark output, or
    None when no fitted calibration exists (raw confidences then
    stand, and the report says so)."""
    if not CALIBRATION_PATH.exists():
        return None
    try:
        data = json.loads(CALIBRATION_PATH.read_text())
        buckets = [
            calibration_mod.CalibrationBucket(
                label=b["bucket"],
                low=0.0,
                high=0.0,
                n=b["n"],
                mean_confidence=b["mean_confidence"],
                accuracy=b["accuracy"],
                calibrated_confidence=b["calibrated_confidence"],
            )
            for b in data["buckets"]
        ]
        # Restore the bucket bounds from the label table.
        for bucket in buckets:
            for low, high, label in calibration_mod.BUCKETS:
                if label == bucket.label:
                    bucket.low, bucket.high = low, high
        return calibration_mod.Calibration(
            buckets=buckets,
            ece_before=data.get("ece_before", 0.0),
            ece_after=data.get("ece_after", 0.0),
            total_pairs=data.get("total_pairs", 0),
            notes=list(data.get("notes", [])),
        )
    except Exception:
        return None


def resolve_with_key_detection(
    result: ParseResult,
    lines: list[str],
    source_document_id: str,
    *,
    paper_identity: dict | None = None,
) -> tuple[AnswerResolution, dict]:
    """Run the trailing-key detector on the key REGION located in
    ``lines`` (M6 key-region location — the whole blob is never
    parsed), resolve the document, and return (resolution,
    key_region_report). When no region is located the key detector
    does not run and the report says so."""
    entries, region = parse_key_entries_in_region(lines)
    key_report = {
        "region": region.to_dict(),
        "entries_parsed": len(entries),
        "entries": {str(k): v for k, v in sorted(entries.items())},
    }
    if not region.located:
        key_report["note"] = "no key region located — key detector did not run"
        resolution = resolve_document_answers(result, [])
        return resolution, key_report
    from app.pipeline.answers.key_detector import detect_trailing_key

    detection = detect_trailing_key(
        region.region_text,
        questions=list(result.questions) + list(result.pending),
        paper_identity=paper_identity,
        source_document_id=source_document_id,
        key_is_bare=True,
        single_paper_in_document=True,
    )
    key_report["detection"] = detection.to_dict()
    resolution = resolve_document_answers(result, list(detection.applied))
    return resolution, key_report


def match_document(
    result: ParseResult,
    resolution: AnswerResolution,
    *,
    calibrator: calibration_mod.Calibration | None = None,
    promoted_numbers: set[int] | None = None,
    promotion_report: PromotionReport | None = None,
) -> MatchedDocument:
    """Build the matched document from a ParseResult + its answer
    resolution. Every resolved MCQ carries its evidence trail;
    promoted questions are flagged; validation runs last."""
    promoted = promoted_numbers or set()
    # Occurrence pairing (see apply_resolution): the resolution
    # list is in document order, so the k-th question with number
    # N takes the k-th verdict for N. Number-only "first verdict"
    # pairing is wrong when numbers repeat across sections
    # (TestPoint: 1375 rows, 476 unique numbers — measured M6
    # end-to-end answer accuracy 0.5084 with the old join).
    by_number: dict[int | None, deque[ResolvedAnswer]] = {}
    for v in resolution.resolved:
        by_number.setdefault(v.question_number, deque()).append(v)
    matched = MatchedDocument()
    for question in result.questions:
        queue = by_number.get(question.number)
        verdict: ResolvedAnswer | None = queue.popleft() if queue else None
        raw_confidence = float(verdict.confidence) if verdict is not None else 0.0
        confidence = (
            calibrator.calibrate(raw_confidence) if calibrator is not None else raw_confidence
        )
        matched.questions.append(
            ResolvedMCQ(
                number=question.number,
                text=question.text,
                options=list(question.options),
                correct_index=verdict.correct_index if verdict is not None else -1,
                answer_source=verdict.source if verdict is not None else "",
                confidence=round(confidence, 3),
                raw_confidence=round(raw_confidence, 3),
                verified=bool(verdict.verified) if verdict is not None else False,
                inferred=bool(verdict.inferred) if verdict is not None else False,
                status=verdict.status if verdict is not None else "unknown",
                kind="mcq",
                page=question.page,
                paper=question.paper,
                duplicate=question.duplicate,
                promoted_from_pending=(
                    question.number in promoted if question.number is not None else False
                ),
                promotion_reason=(
                    f"promoted by ADR-007 rule ({verdict.source}, confidence {raw_confidence})"
                    if question.number in promoted and verdict is not None
                    else ""
                ),
                evidences=[e.to_dict() for e in verdict.evidences] if verdict else [],
                conflicts=list(verdict.conflicts) if verdict else [],
            )
        )
    qa_by_number: dict[int | None, deque[ResolvedAnswer]] = {}
    for v in resolution.qa_resolved:
        qa_by_number.setdefault(v.question_number, deque()).append(v)
    for pair in result.qa_pairs:
        queue = qa_by_number.get(pair.number)
        verdict = queue.popleft() if queue else None
        matched.qa_pairs.append(
            ResolvedMCQ(
                number=pair.number,
                text=pair.question,
                options=[],
                correct_index=-1,
                answer_source="inline",
                confidence=1.0,
                raw_confidence=1.0,
                verified=True,
                inferred=False,
                status="answered",
                kind="qa_pair",
                answer_text=pair.answer,
                page=pair.page,
                paper=pair.paper,
                evidences=[e.to_dict() for e in verdict.evidences] if verdict else [],
            )
        )
    for pending in result.pending:
        matched.pending.append(
            {
                "number": pending.number,
                "text": pending.text,
                "options": list(pending.options),
                "reason": pending.reason,
                "page": pending.page,
                "paper": pending.paper,
            }
        )
    matched.promotion = promotion_report.to_dict() if promotion_report else {}
    matched.counts = {
        "questions": len(matched.questions),
        "answered": matched.answered,
        "unknown": matched.unknown,
        "pending": len(matched.pending),
        "qa_pairs": len(matched.qa_pairs),
        "duplicates": sum(1 for q in matched.questions if q.duplicate),
        "conflicts": sum(1 for q in matched.questions if q.conflicts),
    }
    validate_matched_document(matched)
    return matched


def _lines_from_blocks(blocks: list) -> list[str]:
    lines: list[str] = []
    for block in sorted(
        blocks, key=lambda b: b.reading_order if b.reading_order is not None else 10**6
    ):
        lines.extend(ln for ln in block.text.split("\n") if ln.strip())
    return lines


def _render_scanned_page(pdf_bytes: bytes, page_number: int) -> tuple[bytes, PageQuality]:
    """Render one scanned PDF page at 200 DPI and measure its
    quality. Returns (png_bytes, quality). The caller serialises
    the quality with .to_dict() where a plain dict is needed
    (debug) and passes the object to select_psm (which takes a
    PageQuality, not a dict)."""
    from app.pipeline.pdf.quality import measure_quality, png_to_gray
    from app.pipeline.pdf.renderer import render_pdf_page

    rendered = render_pdf_page(pdf_bytes, page_number, dpi=200)
    quality = measure_quality(png_to_gray(rendered.png_bytes))
    return rendered.png_bytes, quality


def _ocr_page(
    png_bytes: bytes,
    page_number: int,
    settings: Settings,
    *,
    psm: int,
    use_layout: bool,
    analyzer: GeometryLayoutAnalyzer | None = None,
) -> list:
    """OCR one rendered page with Tesseract at the given PSM.
    With ``use_layout`` the geometry layout analyzer orders the
    blocks (two-column reading order); without it the blocks keep
    Tesseract's order ("raw" variant). A failed OCR contributes no
    blocks — per-page failure isolation (M2), never a document
    failure."""
    import uuid as _uuid

    from app.pipeline.interfaces import PageContext
    from app.pipeline.ocr.tesseract import TesseractAdapter

    adapter = TesseractAdapter(
        languages=settings.tesseract_languages,
        psm=psm,
        timeout=settings.tesseract_timeout_seconds,
    )
    context = PageContext(
        document_id=_uuid.uuid4(),
        page_number=page_number,
        storage_path="",
        classification="scanned",
        image_png=png_bytes,
    )
    try:
        blocks = adapter.recognize(context)
    except Exception:
        blocks = []
    if use_layout:
        if analyzer is None:
            from app.pipeline.layout.analyzer import GeometryLayoutAnalyzer

            analyzer = GeometryLayoutAnalyzer()
        layout = analyzer.analyze(context, blocks)
        for region in layout.get("regions", []):
            idx = region["block_index"]
            if 0 <= idx < len(blocks):
                blocks[idx].reading_order = region["reading_order"]
    return sorted(blocks, key=lambda b: b.reading_order if b.reading_order is not None else 10**6)


def _ocr_page_single(
    png_bytes: bytes,
    page_number: int,
    settings: Settings,
    *,
    psm: int,
    use_layout: bool,
    analyzer: GeometryLayoutAnalyzer | None = None,
) -> tuple[list, dict]:
    """Single-path OCR for one page with the M15 confidence-gated
    PSM-4 retry (ADR-008 addendum; rule in app/pipeline/ocr/psm.py):
    OCR at ``psm`` (3), and if the page's mean word confidence is
    below 85, retry with PSM 4 and keep the retry only if its mean
    confidence is strictly higher. Returns (blocks, retry_info)
    where retry_info is {"retried": bool, "kept": bool,
    "mean_conf_psm3": float | None, "mean_conf_psm4": float | None}.
    Multi-pass (M14/ADR-010) must NOT use this — it calls
    _ocr_page directly with its three fixed variants, and a retry
    inside it would change the union. A failed retry contributes
    nothing: _ocr_page already isolates per-page OCR failures, so
    the PSM-3 blocks stand."""
    from app.pipeline.ocr.psm import (
        PSM4_RETRY_PSM,
        keep_psm4_retry,
        mean_word_confidence,
        should_retry_psm4,
    )

    blocks = _ocr_page(
        png_bytes,
        page_number,
        settings,
        psm=psm,
        use_layout=use_layout,
        analyzer=analyzer,
    )
    info: dict = {
        "retried": False,
        "kept": False,
        "mean_conf_psm3": mean_word_confidence(blocks),
        "mean_conf_psm4": None,
    }
    if psm == PSM4_RETRY_PSM:
        return blocks, info
    if not should_retry_psm4(info["mean_conf_psm3"]):
        return blocks, info
    retry_blocks = _ocr_page(
        png_bytes,
        page_number,
        settings,
        psm=PSM4_RETRY_PSM,
        use_layout=use_layout,
        analyzer=analyzer,
    )
    info["retried"] = True
    info["mean_conf_psm4"] = mean_word_confidence(retry_blocks)
    if keep_psm4_retry(info["mean_conf_psm3"], info["mean_conf_psm4"]):
        info["kept"] = True
        return retry_blocks, info
    return blocks, info


def _question_merge_key(question: ExtractedQuestion) -> tuple:
    """Identity of a question across OCR variants: (number,
    stem-prefix). Same number + same stem = the same question
    recovered twice; same number + different stem = a different
    question (multi-section papers restart numbers) and both are
    kept."""
    import re

    stem = re.sub(r"\s+", "", (question.text or "").lower())[:60]
    return (question.number, stem)


def _merge_parse_results(
    results: list[ParseResult], *, labels: list[str]
) -> tuple[ParseResult, dict]:
    """Union-merge ParseResults from OCR variants (M7 multi-pass
    mode). Variant order is priority order: the first variant's
    version of a question wins. Returns (merged, merge_report)
    with per-variant counts and how many questions each later
    variant added. Counters that belong to extraction internals
    (key sections applied, etc.) are taken from the base (first)
    variant and the report says so — the merge only unions
    questions / pending / Q&A pairs."""
    import copy

    base = results[0]
    merged = ParseResult(
        questions=list(base.questions),
        qa_pairs=list(base.qa_pairs),
        pending=list(base.pending),
        skipped=list(base.skipped),
        excluded=list(base.excluded),
        format_counts=dict(base.format_counts),
        answer_sources=dict(base.answer_sources),
        key_sections_found=base.key_sections_found,
        key_entries_applied=base.key_entries_applied,
        unmatched_key_entries=list(base.unmatched_key_entries),
        conflicts=list(base.conflicts),
        number_gaps=list(base.number_gaps),
        number_duplicates=list(base.number_duplicates),
        notes=list(base.notes),
        noise_lines_filtered=base.noise_lines_filtered,
        five_option_normalised=base.five_option_normalised,
    )
    seen_questions = {_question_merge_key(q) for q in merged.questions}
    seen_pending = {
        (p.number, (p.text or "")[:60].replace(" ", "").lower()) for p in merged.pending
    }
    seen_qa = {
        (p.number, (p.question or "")[:60].replace(" ", "").lower()) for p in merged.qa_pairs
    }
    added_by_variant: dict[str, int] = {}
    for label, variant in zip(labels[1:], results[1:], strict=True):
        added = 0
        for question in variant.questions:
            key = _question_merge_key(question)
            if key not in seen_questions:
                seen_questions.add(key)
                merged.questions.append(copy.copy(question))
                added += 1
        for pending in variant.pending:
            key = (pending.number, (pending.text or "")[:60].replace(" ", "").lower())
            if key not in seen_pending:
                seen_pending.add(key)
                merged.pending.append(copy.copy(pending))
                added += 1
        for pair in variant.qa_pairs:
            key = (pair.number, (pair.question or "")[:60].replace(" ", "").lower())
            if key not in seen_qa:
                seen_qa.add(key)
                merged.qa_pairs.append(copy.copy(pair))
                added += 1
        added_by_variant[label] = added
    # Recompute gaps/duplicates from the merged set (the base
    # variant's lists no longer describe it).
    numbers = [q.number for q in merged.questions if q.number is not None]
    numbers += [p.number for p in merged.pending if p.number is not None]
    distinct = sorted(set(numbers))
    merged.number_gaps = [
        str(n) for n in range(1, (max(distinct) + 1 if distinct else 1)) if n not in distinct
    ]
    from collections import Counter

    merged.number_duplicates = [str(n) for n, c in sorted(Counter(numbers).items()) if c > 1]
    merge_report = {
        "mode": "multi-pass-union",
        "variants": list(labels),
        "variant_questions": [len(r.questions) for r in results],
        "variant_pending": [len(r.pending) for r in results],
        "added_by_variant": added_by_variant,
        "merged_questions": len(merged.questions),
        "merged_pending": len(merged.pending),
        "counters_from_base_variant": labels[0],
    }
    return merged, merge_report


def _finish_parse(
    result: ParseResult,
    lines: list[str],
    source_document_id: str,
    *,
    promote: bool = True,
    debug_extra: dict | None = None,
    on_stage: Callable[[str, dict], None] | None = None,
) -> tuple[MatchedDocument, dict, dict]:
    """The shared tail of every parse path (PDF, multi-pass,
    image): key-region-located key detection -> resolution ->
    promotion -> matching -> validation -> report. Returns
    (matched, report, debug). ``on_stage`` (M7) is called with
    (stage_name, detail) at each phase boundary so the background
    worker can record real stage progress and enforce timeouts /
    cancellation; it is never called with file contents or OCR
    text."""
    if on_stage is not None:
        on_stage("answers", {"questions": len(result.questions)})
    resolution, key_report = resolve_with_key_detection(result, lines, source_document_id)
    apply_resolution(result, resolution)
    if promote:
        promotion_report = promote_pending(result, resolution)
    else:
        promotion_report = PromotionReport()
    if on_stage is not None:
        on_stage(
            "matching",
            {"answered": resolution.answered, "promoted": len(promotion_report.promoted)},
        )
    promoted_numbers = set(promotion_report.promoted)
    calibrator = load_calibration()
    matched = match_document(
        result,
        resolution,
        calibrator=calibrator,
        promoted_numbers=promoted_numbers,
        promotion_report=promotion_report,
    )
    if on_stage is not None:
        on_stage("report", {"questions": len(matched.questions)})
    if calibrator is not None:
        matched.notes.append("confidences calibrated (m6-calibration.json)")
    else:
        matched.notes.append("no fitted calibration found — raw confidences reported")
    report = build_document_report(
        matched,
        document_label=source_document_id,
        promotion=promotion_report.to_dict(),
        key_region=key_report["region"],
    )
    debug = {
        "key": key_report,
        "promotion": promotion_report.to_dict(),
    }
    if debug_extra:
        debug.update(debug_extra)
    return matched, report, debug


def _classify_pdf_pages(pdf_bytes: bytes) -> tuple[list, int]:
    """A1: per-page classification from PyMuPDF evidence (never the
    document-level total_chars heuristic). Returns
    (classifications, total_text_chars) — the char total is kept for
    debug only; it no longer decides anything."""
    from app.pipeline.pdf.analysis import analyze_pdf
    from app.pipeline.pdf.classifier import classify_pages_from_analysis

    analysis = analyze_pdf(pdf_bytes)
    classifications = classify_pages_from_analysis(analysis.pages)
    total_chars = sum(p.text_char_count for p in analysis.pages)
    return classifications, total_chars


def _route_pdf_pages(classifications: list, settings: Settings) -> dict[int, list[str]]:
    """A1: route each classified page through the router (ADR-002).
    Returns {page_number: [engine names]}. This parse path can only
    run digital-pymupdf + tesseract, so those are the available
    engines — PaddleOCR is never a routing target here (it is not
    instantiated by this path), and the deployment gate still
    applies to whatever is listed."""
    from app.pipeline.ocr.deployment import deployment_profile_from_settings
    from app.pipeline.ocr.router import route_page

    available = ["digital-pymupdf", "tesseract"]
    deployment = deployment_profile_from_settings(settings)
    return {
        cls.page_number: route_page(cls.classification, available, deployment)
        for cls in classifications
    }


def _repeated_line_texts(blocks_by_page: dict[int, list], *, min_pages: int = 3) -> set[str]:
    """Normalised digital line texts that repeat on >= min_pages
    distinct pages. Watermarks and running headers repeat verbatim;
    question text never repeats across pages, so a repeated line is
    furniture, not content."""
    from collections import Counter

    counts: Counter[str] = Counter()
    for blocks in blocks_by_page.values():
        seen: set[str] = set()
        for block in blocks:
            for line in block.text.split("\n"):
                norm = " ".join(line.strip().lower().split())
                if norm:
                    seen.add(norm)
        counts.update(seen)
    return {line for line, n in counts.items() if n >= min_pages}


def _drop_furniture_blocks(blocks: list, furniture: set[str]) -> tuple[list, int]:
    """Drop digital blocks whose every line is repeated furniture
    (A1: watermark-only text must not become questions). A block
    mixing furniture with real text is kept whole — partial drops
    would shift the block's per-line bold indices."""
    kept: list = []
    dropped = 0
    for block in blocks:
        lines = [ln for ln in block.text.split("\n") if ln.strip()]
        if lines and all(" ".join(ln.strip().lower().split()) in furniture for ln in lines):
            dropped += 1
            continue
        kept.append(block)
    return kept, dropped


def _merge_page_blocks(digital_blocks: list, ocr_blocks: list) -> list:
    """A1: merge one mixed page's exact digital blocks with its
    (deduped) OCR blocks, then re-derive reading order from the
    block bboxes — the two engines number reading_order from 0
    independently, so their orders cannot just be concatenated.
    Blocks are copied; the shared digital blocks are never mutated
    (multi-pass reuses them across variants)."""
    import copy

    from app.pipeline.layout.columns import reading_order_indices

    merged = [copy.copy(b) for b in digital_blocks] + [copy.copy(b) for b in ocr_blocks]
    bboxes = [b.bbox for b in merged]
    if any(b is None for b in bboxes):
        return merged
    ranks = reading_order_indices(bboxes)
    ordered = sorted(enumerate(merged), key=lambda pair: ranks[pair[0]])
    for rank, (_index, block) in enumerate(ordered):
        block.reading_order = rank
    return [block for _index, block in ordered]


def _build_page_lines(
    digital_blocks_by_page: dict[int, list],
    ocr_blocks_by_page: dict[int, list],
    page_count: int,
) -> list:
    """A1: one PageLines per page that produced blocks. Mixed pages
    carry digital + OCR blocks together (is_ocr=True — the page
    needed OCR); pure digital pages carry is_ocr=False. Pages with
    no blocks are skipped (they contribute no lines either way)."""
    from app.pipeline.extract.service import PageLines

    pages = []
    for page_number in range(1, page_count + 1):
        digital = digital_blocks_by_page.get(page_number)
        ocr = ocr_blocks_by_page.get(page_number)
        if digital and ocr:
            blocks = _merge_page_blocks(digital, ocr)
            pages.append(PageLines(page_number=page_number, blocks=blocks, is_ocr=True))
        elif digital:
            pages.append(PageLines(page_number=page_number, blocks=digital, is_ocr=False))
        elif ocr:
            pages.append(PageLines(page_number=page_number, blocks=ocr, is_ocr=True))
    return pages


def parse_document_bytes(
    pdf_bytes: bytes,
    source_document_id: str,
    *,
    settings: Settings | None = None,
    psm_override: int | None = None,
    promote: bool = True,
    multi_pass: bool = False,
    on_stage: Callable[[str, dict], None] | None = None,
) -> tuple[MatchedDocument, dict, dict]:
    """Parse one PDF's bytes end to end (in-process, synchronous):
    per-page routing (A1) — every page is classified on its own
    PyMuPDF evidence and routed through ``route_page``: digital
    pages take the exact digital extractor, scanned / mixed /
    unknown / unreadable pages take per-page Tesseract OCR with
    per-page PSM selection, blank pages take nothing. The old
    document-level ``total_chars >= 100`` rule is gone: a scanned
    paper whose repeated watermark text summed past 100 chars was
    misread as digital and OCR never ran (NOA Maths: 13 pages,
    0 questions). Then layout, extraction, key-region-located key
    detection, resolution, promotion, matching, validation.
    Returns (matched, report, debug) where debug carries the key
    region, the per-page PSM choices, the per-page classifications
    and routes, and the promotion report. Raises ValueError on an
    unreadable PDF; OCR failures are per-page (a failed page
    contributes no blocks, never fails the document).
    ``psm_override`` forces one PSM on every scanned page instead
    of the per-page selection (benchmarking / debug only — the
    parse API never sets it). ``promote=False`` skips
    pending-question promotion (benchmarking only — the parse API
    always promotes); the promotion report is then empty and
    pendings stay pending. ``multi_pass=True`` (M7, optional,
    never the default) runs three OCR variants — PSM 3 + layout,
    PSM 3 raw, PSM 4 raw — on the OCR-routed pages only, and
    union-merges the recovered questions (M5 measured 59/100 vs
    41/100 single-path, at 2–3x OCR cost); the key is still
    detected on the layout variant's lines only."""
    from app.pipeline.extract.service import extract_document
    from app.pipeline.interfaces import PageContext
    from app.pipeline.ocr.digital import DigitalExtractor
    from app.pipeline.ocr.psm import select_psm
    from app.pipeline.ocr.router import deduplicate_blocks

    settings = settings or Settings()
    classifications, total_chars = _classify_pdf_pages(pdf_bytes)
    page_count = len(classifications)
    routes = _route_pdf_pages(classifications, settings)
    # "Digital" now means no page needed OCR at all (every page
    # digital). A mixed document is not digital — its scanned pages
    # were OCR'd. A zero-page PDF has no digital pages either.
    is_digital = page_count > 0 and all(
        routes[p] == ["digital-pymupdf"] for p in range(1, page_count + 1)
    )
    if on_stage is not None:
        on_stage(
            "classify",
            {
                "is_digital": is_digital,
                "page_count": page_count,
                "page_classifications": {
                    str(c.page_number): c.classification for c in classifications
                },
            },
        )
    # Exact digital blocks, collected once, for every page the router
    # sends to the digital extractor (shared across multi-pass
    # variants — the digital text does not change per variant).
    extractor = DigitalExtractor()
    digital_blocks_by_page: dict[int, list] = {}
    for page_number in range(1, page_count + 1):
        if "digital-pymupdf" not in routes[page_number]:
            continue
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
        digital_blocks_by_page[page_number] = blocks
    # A1: on a mixed page the text layer is usually furniture — a
    # watermark repeated on every page. Drop whole digital blocks
    # made only of lines that repeat on >= 3 pages, so watermark
    # text cannot become questions. Pure digital pages keep their
    # blocks untouched (their behaviour is unchanged from before A1).
    mixed_pages = [
        p for p in range(1, page_count + 1) if routes[p] == ["digital-pymupdf", "tesseract"]
    ]
    furniture_blocks_dropped = 0
    if mixed_pages:
        furniture = _repeated_line_texts(digital_blocks_by_page)
        for page_number in mixed_pages:
            kept, dropped = _drop_furniture_blocks(
                digital_blocks_by_page.get(page_number, []), furniture
            )
            digital_blocks_by_page[page_number] = kept
            furniture_blocks_dropped += dropped
    ocr_pages = [
        page_number
        for page_number in range(1, page_count + 1)
        if "tesseract" in routes[page_number]
    ]
    has_digital_pages = bool(digital_blocks_by_page)
    all_blocks: list = []
    lines: list[str] = []
    psm_by_page: dict[int, int] = {}
    quality_by_page: dict[int, dict] = {}
    merge_report: dict | None = None
    psm4_retry_by_page: dict[int, dict] = {}
    if not ocr_pages:
        # Fully digital document: the pre-A1 digital path, unchanged
        # (same extractor, same pdfplumber table fallback).
        result = extract_document(
            _build_page_lines(digital_blocks_by_page, {}, page_count),
            source_document_id,
            pdf_bytes=pdf_bytes,
        )
        if on_stage is not None:
            on_stage(
                "extract",
                {"questions": len(result.questions), "pending": len(result.pending)},
            )
        for page_number in range(1, page_count + 1):
            page_blocks = digital_blocks_by_page.get(page_number, [])
            all_blocks.extend(page_blocks)
            lines.extend(_lines_from_blocks(page_blocks))
    elif multi_pass:
        # Three OCR variants, OCR-routed pages only: (PSM 3 +
        # layout), (PSM 3 raw), (PSM 4 raw) — the M5 full-run
        # experiment's variants. M7 optimisation (measured: render
        # is ~8.5s of a 130s parse, and the old code paid it 3x):
        # each page is rendered ONCE and the same PNG bytes are
        # OCR'd by all three variants. Digital pages contribute the
        # same exact blocks to every variant, so the union keeps
        # them once (merge dedup by question key).
        from app.pipeline.layout.analyzer import GeometryLayoutAnalyzer

        analyzer = GeometryLayoutAnalyzer()
        variants: list[tuple[str, int, bool]] = [
            ("psm3-layout", 3, True),
            ("psm3-raw", 3, False),
            ("psm4-raw", 4, False),
        ]
        renders: dict[int, bytes] = {}
        for page_number in ocr_pages:
            png_bytes, quality = _render_scanned_page(pdf_bytes, page_number)
            renders[page_number] = png_bytes
            quality_by_page[page_number] = quality.to_dict()
            psm_by_page[page_number] = variants[0][1]
            if on_stage is not None:
                on_stage("render", {"page": page_number})
        variant_results: list[ParseResult] = []
        variant_labels: list[str] = []
        variant_seconds: dict[str, float] = {}
        for label, psm, use_layout in variants:
            import time as _time

            started = _time.monotonic()
            v_ocr_blocks: dict[int, list] = {}
            for page_number in ocr_pages:
                blocks = _ocr_page(
                    renders[page_number],
                    page_number,
                    settings,
                    psm=psm,
                    use_layout=use_layout,
                    analyzer=analyzer,
                )
                if on_stage is not None:
                    on_stage("ocr", {"page": page_number, "psm": psm, "variant": label})
                    if use_layout:
                        on_stage("layout", {"page": page_number, "variant": label})
                if page_number in mixed_pages:
                    # A1 (router rule): OCR blocks duplicating the
                    # exact digital blocks are dropped — digital wins.
                    blocks, _dropped = deduplicate_blocks(
                        digital_blocks_by_page.get(page_number, []), blocks
                    )
                v_ocr_blocks[page_number] = blocks
            variant_pages = _build_page_lines(digital_blocks_by_page, v_ocr_blocks, page_count)
            variant_results.append(
                extract_document(
                    variant_pages,
                    source_document_id,
                    pdf_bytes=pdf_bytes if has_digital_pages else None,
                )
            )
            variant_labels.append(label)
            variant_seconds[label] = round(_time.monotonic() - started, 1)
            if label == "psm3-layout":
                all_blocks = [block for page in variant_pages for block in (page.blocks or [])]
                lines = []
                for page in variant_pages:
                    lines.extend(_lines_from_blocks(page.blocks or []))
        result, merge_report = _merge_parse_results(variant_results, labels=variant_labels)
        merge_report["variant_seconds"] = variant_seconds
        if on_stage is not None:
            on_stage(
                "extract",
                {"questions": len(result.questions), "pending": len(result.pending)},
            )
    else:
        from app.pipeline.layout.analyzer import GeometryLayoutAnalyzer

        analyzer = GeometryLayoutAnalyzer()
        ocr_blocks_by_page: dict[int, list] = {}
        for page_number in ocr_pages:
            png_bytes, quality = _render_scanned_page(pdf_bytes, page_number)
            quality_by_page[page_number] = quality.to_dict()
            psm = psm_override if psm_override is not None else select_psm(quality)
            psm_by_page[page_number] = psm
            if on_stage is not None:
                on_stage("render", {"page": page_number})
            # Single path only: M15 confidence-gated PSM-4 retry
            # (ADR-008 addendum). Multi-pass above calls _ocr_page
            # directly and is untouched.
            blocks, retry_info = _ocr_page_single(
                png_bytes,
                page_number,
                settings,
                psm=psm,
                use_layout=True,
                analyzer=analyzer,
            )
            psm4_retry_by_page[page_number] = retry_info
            if on_stage is not None:
                on_stage("ocr", {"page": page_number, "psm": psm})
                on_stage("layout", {"page": page_number})
            if page_number in mixed_pages:
                # A1 (router rule): OCR blocks duplicating the exact
                # digital blocks are dropped — the digital text wins.
                blocks, _dropped = deduplicate_blocks(
                    digital_blocks_by_page.get(page_number, []), blocks
                )
            ocr_blocks_by_page[page_number] = blocks
        pages = _build_page_lines(digital_blocks_by_page, ocr_blocks_by_page, page_count)
        result = extract_document(
            pages,
            source_document_id,
            pdf_bytes=pdf_bytes if has_digital_pages else None,
        )
        if on_stage is not None:
            on_stage(
                "extract",
                {"questions": len(result.questions), "pending": len(result.pending)},
            )
        for page in pages:
            all_blocks.extend(page.blocks or [])
            lines.extend(_lines_from_blocks(page.blocks or []))
    matched, report, debug = _finish_parse(
        result,
        lines,
        source_document_id,
        promote=promote,
        on_stage=on_stage,
        debug_extra={
            "is_digital": is_digital,
            "total_text_chars": total_chars,
            "page_count": page_count,
            "psm_override": psm_override,
            "psm_by_page": {str(k): v for k, v in psm_by_page.items()},
            "quality_by_page": quality_by_page,
            "psm4_retry_by_page": {str(k): v for k, v in psm4_retry_by_page.items()},
            "multi_pass": multi_pass,
            "merge": merge_report,
            "page_classifications": {str(c.page_number): c.classification for c in classifications},
            "page_routes": {str(p): routes[p] for p in range(1, page_count + 1)},
            "furniture_blocks_dropped": furniture_blocks_dropped,
        },
    )
    return matched, report, debug


#: Image magic bytes accepted by the image parse path.
IMAGE_MAGIC = (b"\x89PNG", b"\xff\xd8\xff")


def parse_image_bytes(
    image_bytes: bytes,
    source_document_id: str,
    *,
    settings: Settings | None = None,
    psm_override: int | None = None,
    promote: bool = True,
    multi_pass: bool = False,
    on_stage: Callable[[str, dict], None] | None = None,
) -> tuple[MatchedDocument, dict, dict]:
    """Parse one photo's bytes end to end (JPEG/PNG): the image is
    one scanned page — decode, measure quality, Tesseract OCR,
    layout, extraction, key detection, resolution, promotion,
    matching, validation. Returns the same (matched, report,
    debug) shape as :func:`parse_document_bytes` (``is_digital``
    False, ``page_count`` 1). Raises ValueError on undecodable or
    non-image bytes. This is the server side of the Flutter
    ``importImage`` path (M7); the photo itself is never stored,
    only the parsed MCQs. ``multi_pass=True`` (M14, ADR-010)
    runs the same three OCR variants as the PDF path — PSM 3 +
    layout, PSM 3 raw, PSM 4 raw — and union-merges the
    recovered questions; the default stays the single path."""
    from app.pipeline.extract.service import extract_from_ocr_blocks
    from app.pipeline.layout.analyzer import GeometryLayoutAnalyzer
    from app.pipeline.ocr.psm import select_psm
    from app.pipeline.pdf.quality import measure_quality, png_to_gray

    settings = settings or Settings()
    if not image_bytes.startswith(IMAGE_MAGIC):
        raise ValueError("Upload must be a JPEG or PNG image.")
    # Normalise to PNG bytes (Tesseract takes PNG); Pillow decodes
    # both JPEG and PNG. A corrupt image raises here -> ValueError.
    try:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(image_bytes)) as image:
            image.load()
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, format="PNG")
            png_bytes = buffer.getvalue()
    except Exception as exc:
        raise ValueError(f"Image could not be decoded: {exc}") from exc
    quality = measure_quality(png_to_gray(png_bytes))
    psm = psm_override if psm_override is not None else select_psm(quality)
    psm4_retry_by_page: dict[int, dict] = {}
    if on_stage is not None:
        on_stage("classify", {"is_digital": False, "page_count": 1})
        on_stage("render", {"page": 1})
    merge_report: dict | None = None
    if multi_pass:
        # Same three variants as the PDF multi-pass path
        # (ADR-010): the one image is OCR'd three ways and the
        # recovered questions are union-merged.
        import time as _time

        analyzer = GeometryLayoutAnalyzer()
        variants: list[tuple[str, int, bool]] = [
            ("psm3-layout", 3, True),
            ("psm3-raw", 3, False),
            ("psm4-raw", 4, False),
        ]
        variant_results: list[ParseResult] = []
        variant_labels: list[str] = []
        variant_seconds: dict[str, float] = {}
        lines: list[str] = []
        for label, variant_psm, use_layout in variants:
            started = _time.monotonic()
            blocks = _ocr_page(
                png_bytes,
                1,
                settings,
                psm=variant_psm,
                use_layout=use_layout,
                analyzer=analyzer,
            )
            if on_stage is not None:
                on_stage("ocr", {"page": 1, "psm": variant_psm, "variant": label})
                if use_layout:
                    on_stage("layout", {"page": 1, "variant": label})
            if label == "psm3-layout":
                lines = _lines_from_blocks(blocks)
            variant_results.append(extract_from_ocr_blocks(blocks, source_document_id))
            variant_labels.append(label)
            variant_seconds[label] = round(_time.monotonic() - started, 1)
        result, merge_report = _merge_parse_results(variant_results, labels=variant_labels)
        merge_report["variant_seconds"] = variant_seconds
        psm = variants[0][1]
    else:
        # Single path only: M15 confidence-gated PSM-4 retry
        # (ADR-008 addendum). Multi-pass above calls _ocr_page
        # directly and is untouched.
        blocks, retry_info = _ocr_page_single(
            png_bytes,
            1,
            settings,
            psm=psm,
            use_layout=True,
            analyzer=GeometryLayoutAnalyzer(),
        )
        if on_stage is not None:
            on_stage("ocr", {"page": 1, "psm": psm})
            on_stage("layout", {"page": 1})
        lines = _lines_from_blocks(blocks)
        result = extract_from_ocr_blocks(blocks, source_document_id)
        psm4_retry_by_page[1] = retry_info
    if on_stage is not None:
        on_stage(
            "extract",
            {"questions": len(result.questions), "pending": len(result.pending)},
        )
    matched, report, debug = _finish_parse(
        result,
        lines,
        source_document_id,
        promote=promote,
        on_stage=on_stage,
        debug_extra={
            "is_digital": False,
            "total_text_chars": 0,
            "page_count": 1,
            "psm_override": psm_override,
            "psm_by_page": {"1": psm},
            "quality_by_page": {1: quality.to_dict()},
            "psm4_retry_by_page": {"1": psm4_retry_by_page.get(1, {})},
            "multi_pass": multi_pass,
            "merge": merge_report,
        },
    )
    return matched, report, debug
