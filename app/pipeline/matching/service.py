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
from pathlib import Path

from app.config import Settings
from app.pipeline.answers.models import ResolvedAnswer
from app.pipeline.answers.service import (
    AnswerResolution,
    apply_resolution,
    resolve_document_answers,
)
from app.pipeline.extract.models import ParseResult
from app.pipeline.matching import calibration as calibration_mod
from app.pipeline.matching.key_region import parse_key_entries_in_region
from app.pipeline.matching.models import MatchedDocument, ResolvedMCQ
from app.pipeline.matching.promotion import PromotionReport, promote_pending
from app.pipeline.matching.report import build_document_report
from app.pipeline.matching.validate import validate_matched_document

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


def parse_document_bytes(
    pdf_bytes: bytes,
    source_document_id: str,
    *,
    settings: Settings | None = None,
    psm_override: int | None = None,
    promote: bool = True,
) -> tuple[MatchedDocument, dict, dict]:
    """Parse one PDF's bytes end to end (in-process, synchronous):
    digital text layer first, else per-page Tesseract OCR with
    per-page PSM selection, layout, extraction, key-region-located
    key detection, resolution, promotion, matching, validation.
    Returns (matched, report, debug) where debug carries the key
    region, the per-page PSM choices, and the promotion report.
    Raises ValueError on an unreadable PDF; OCR failures are
    per-page (a failed page contributes no blocks, never fails the
    document). ``psm_override`` forces one PSM on every scanned
    page instead of the per-page selection (benchmarking / debug
    only — the parse API never sets it). ``promote=False`` skips
    pending-question promotion (benchmarking only — the parse API
    always promotes); the promotion report is then empty and
    pendings stay pending."""
    import fitz

    from app.pipeline.extract.service import (
        extract_from_digital_pdf,
        extract_from_ocr_blocks,
    )
    from app.pipeline.interfaces import PageContext
    from app.pipeline.layout.analyzer import GeometryLayoutAnalyzer
    from app.pipeline.ocr.psm import select_psm
    from app.pipeline.ocr.tesseract import TesseractAdapter
    from app.pipeline.pdf.quality import measure_quality, png_to_gray
    from app.pipeline.pdf.renderer import render_pdf_page

    settings = settings or Settings()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = len(doc)
    total_chars = sum(len(doc[i].get_text()) for i in range(page_count))
    doc.close()
    # Digital when the text layer carries real content (>= 100 chars
    # total — PPSC-66's scanned pages carry ~11 chars of watermark
    # text, CA40 carries thousands). Below that the text layer is
    # furniture, not content: OCR the renders instead.
    is_digital = total_chars >= 100
    all_blocks: list = []
    lines: list[str] = []
    psm_by_page: dict[int, int] = {}
    quality_by_page: dict[int, dict] = {}
    if is_digital:
        result = extract_from_digital_pdf(pdf_bytes, source_document_id)
        from app.pipeline.ocr.digital import DigitalExtractor

        extractor = DigitalExtractor()
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
            lines.extend(_lines_from_blocks(blocks))
    else:
        analyzer = GeometryLayoutAnalyzer()
        for page_number in range(1, page_count + 1):
            rendered = render_pdf_page(pdf_bytes, page_number, dpi=200)
            quality = measure_quality(png_to_gray(rendered.png_bytes))
            quality_by_page[page_number] = quality.to_dict()
            psm = psm_override if psm_override is not None else select_psm(quality)
            psm_by_page[page_number] = psm
            adapter = TesseractAdapter(languages=settings.tesseract_languages, psm=psm)
            context = PageContext(
                document_id=uuid.uuid4(),
                page_number=page_number,
                storage_path="",
                classification="scanned",
                image_png=rendered.png_bytes,
            )
            try:
                blocks = adapter.recognize(context)
            except Exception:
                blocks = []
            layout = analyzer.analyze(context, blocks)
            for region in layout.get("regions", []):
                idx = region["block_index"]
                if 0 <= idx < len(blocks):
                    blocks[idx].reading_order = region["reading_order"]
            ordered = sorted(
                blocks,
                key=lambda b: b.reading_order if b.reading_order is not None else 10**6,
            )
            all_blocks.extend(ordered)
            lines.extend(_lines_from_blocks(ordered))
        result = extract_from_ocr_blocks(all_blocks, source_document_id)
    resolution, key_report = resolve_with_key_detection(result, lines, source_document_id)
    apply_resolution(result, resolution)
    if promote:
        promotion_report = promote_pending(result, resolution)
    else:
        promotion_report = PromotionReport()
    promoted_numbers = set(promotion_report.promoted)
    calibrator = load_calibration()
    matched = match_document(
        result,
        resolution,
        calibrator=calibrator,
        promoted_numbers=promoted_numbers,
        promotion_report=promotion_report,
    )
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
        "is_digital": is_digital,
        "total_text_chars": total_chars,
        "page_count": page_count,
        "psm_override": psm_override,
        "psm_by_page": {str(k): v for k, v in psm_by_page.items()},
        "quality_by_page": quality_by_page,
        "key": key_report,
        "promotion": promotion_report.to_dict(),
    }
    return matched, report, debug
