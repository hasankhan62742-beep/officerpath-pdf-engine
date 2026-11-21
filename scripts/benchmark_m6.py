# OfficerPath AI — M6 benchmark (2026-11-22).
#
# Measures the M6 matching layer end to end on the golden set:
# - Resolved-MCQ accuracy (stem + 4 options + answer) on the
#   digital fixtures (TestPoint, Computer Q&A, CA40, Urdu NOA,
#   monthly CA) + PPSC-66 live OCR + Paper 60 photo.
# - Before/after pending-question promotion (ADR-007).
# - Before/after key-region location (live PPSC-66 key FPs).
# - Confidence calibration: bucket vs actual accuracy, ECE
#   before/after (fitted mapping written to
#   docs/benchmarks/m6-calibration.json for the parse endpoint).
# - PPSC-66 recovery before/after per-page PSM routing (ADR-008:
#   expected identical — the routing hook returns PSM 3).
# - TestPoint residual FPs (M5: 28).
#
# ALL numbers are measured in this run, on THIS VM (labelled VM
# numbers — NOT Render numbers). Anything unmeasured is reported
# as UNVERIFIED. No PaddleOCR (ADR-005). No Gemini API calls; the
# stored Gemini reference texts are ground truth for the PPSC-66
# key and the Paper 60 stars, where noted.
#
# Usage: .venv/bin/python scripts/benchmark_m6.py
# Output: docs/benchmarks/m6-benchmark-2026-11-22.json +
#         docs/benchmarks/m6-calibration.json + stdout summary.

from __future__ import annotations

import json
import re
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from benchmark_m4 import (  # noqa: E402
    _load_ca40,
    _load_computer,
    _load_testpoint,
    _load_urdu_noa,
    _match_pairs,
    _prf,
    _score_mcq,
    _score_qa,
)
from benchmark_m5 import _paper60_questions, _peak_rss_mb, _ppsc66_key_gt  # noqa: E402

from app.pipeline.matching.calibration import fit_calibration  # noqa: E402
from app.pipeline.matching.service import parse_document_bytes  # noqa: E402

FIX = Path("app/tests/fixtures/golden")
PPSC66_DIR = FIX / "ppsc66"
#: The PPSC-66 PDF itself lives in the Flutter app's fixtures, not
#: the engine's (same split as benchmark_m4/m5).
FLUTTER_FIX = Path.home() / "workspace/officerpath-ai/test-fixtures/ppsc66"
OUT = Path("docs/benchmarks/m6-benchmark-2026-11-22.json")
CAL_OUT = Path("docs/benchmarks/m6-calibration.json")
PSM_EXPERIMENT = Path("docs/benchmarks/m6-psm-experiment.json")
PSM_EXPERIMENT_TMP = Path("/tmp/m6-psm-experiment.json")
KEY_LINES_OUT = Path("/tmp/m6-p66-key-lines.txt")


def _gt_answer_index(gt_entry: dict) -> int | None:
    letter = gt_entry.get("answer")
    if isinstance(letter, str) and len(letter) == 1 and "A" <= letter <= "D":
        return ord(letter) - 65
    return None


def _calibration_points(
    matched_questions: list[dict], gt: list[dict], *, by_number: bool = False
) -> list[tuple[float, bool]]:
    """(confidence, correct) pairs for matched questions whose GT
    answer is known. Unknown answers are excluded, never guessed.

    Pairing is by number AND stem similarity (>= 0.85, the same
    pairing ``_score_mcq`` uses) — number-only pairing is WRONG
    here: TestPoint Sr# restarts per section (1375 rows, 476
    unique numbers), so a detected Q5 would pair with the wrong
    section's GT Q5. Measured (M6 run 2): number-only pairing
    gave accuracy 0.392 at confidence 1.0 — a harness artifact,
    not a detector finding. ``by_number`` is only for the PPSC-66
    live key GT, whose entries have no stems (text "") and unique
    numbers 1..100, so number pairing is valid there.

    Confidence is the RAW confidence (``raw_confidence``), never
    the calibrated one: the benchmark must measure the detectors,
    not fit its own previous output. Measured (M6 run 3): the
    run-2 fit (1.0 -> 0.392) was still on disk, the parses loaded
    it, and the points came out at mean confidence 0.392 — the
    fit chasing its own tail."""
    points: list[tuple[float, bool]] = []
    if by_number:
        by_num = {g["number"]: g for g in gt if g.get("number") is not None}
        pairs = [(q, by_num[q["number"]]) for q in matched_questions if q.get("number") in by_num]
    else:
        pairs = _match_pairs(matched_questions, gt)
    for q, g in pairs:
        expected = _gt_answer_index(g)
        if expected is None:
            continue
        if q.get("correct_index", -1) < 0:
            continue  # unanswered: no prediction to calibrate
        raw = q.get("raw_confidence", q.get("confidence", 0.0))
        points.append((float(raw), q["correct_index"] == expected))
    return points


def _end_to_end_digital(
    pdf_name: str, gt: list[dict], *, score_answers: bool, source_id: str
) -> tuple[dict, list[tuple[float, bool]]]:
    """Parse one digital PDF end to end and score it. Returns
    (result, calibration points) — the points are the matched
    questions' (confidence, correct) pairs, used by the fit."""
    pdf = (PPSC66_DIR / pdf_name).read_bytes()
    start = time.monotonic()
    matched, report, debug = parse_document_bytes(pdf, source_id)
    seconds = round(time.monotonic() - start, 1)
    detected = [q.to_dict() for q in matched.questions]
    score = _score_mcq(detected, gt, score_answers=score_answers)
    points = _calibration_points(detected, gt) if score_answers else []
    return {
        "seconds": seconds,
        "is_digital": debug["is_digital"],
        "counts": matched.counts,
        "promotion": matched.promotion,
        "validation_issues": len(matched.validation_issues),
        "score": score,
        "calibration_points": len(points),
    }, points


def _promotion_before_after(pdf: bytes, source_id: str) -> dict:
    """Same document parsed twice: promotion off vs on. Everything
    else identical, so the delta IS the promotion effect."""
    before, _, _ = parse_document_bytes(pdf, source_id, promote=False)
    after, _, _ = parse_document_bytes(pdf, source_id, promote=True)
    return {
        "before": {
            "answered": before.answered,
            "unknown": before.unknown,
            "pending": len(before.pending),
            "questions": len(before.questions),
        },
        "after": {
            "answered": after.answered,
            "unknown": after.unknown,
            "pending": len(after.pending),
            "questions": len(after.questions),
        },
        "promoted": after.promotion.get("promoted", []),
        "promoted_count": after.promotion.get("promoted_count", 0),
        "skipped": after.promotion.get("skipped", []),
    }


def _live_p66_key_lines() -> list[str]:
    """Live OCR lines of PPSC-66 p6+p7 (PSM 3, layout-ordered) —
    the same text the M5 live key measurement used, re-measured
    now that tesseract is installed again."""
    import fitz  # noqa: F401  (kept for parity with the M5 live path)

    from app.config import Settings
    from app.pipeline.interfaces import PageContext
    from app.pipeline.layout.analyzer import GeometryLayoutAnalyzer
    from app.pipeline.ocr.tesseract import TesseractAdapter
    from app.pipeline.pdf.renderer import render_pdf_page

    settings = Settings()
    pdf = (FLUTTER_FIX / "ppsc_paper_66.pdf").read_bytes()
    adapter = TesseractAdapter(languages=settings.tesseract_languages, psm=settings.tesseract_psm)
    analyzer = GeometryLayoutAnalyzer()
    lines: list[str] = []
    for page_number in (6, 7):
        rendered = render_pdf_page(pdf, page_number, dpi=200)
        context = PageContext(
            document_id=uuid.uuid4(),
            page_number=page_number,
            storage_path="",
            classification="scanned",
            image_png=rendered.png_bytes,
        )
        blocks = adapter.recognize(context)
        layout = analyzer.analyze(context, blocks)
        for region in layout.get("regions", []):
            idx = region["block_index"]
            if 0 <= idx < len(blocks):
                blocks[idx].reading_order = region["reading_order"]
        ordered = sorted(
            blocks,
            key=lambda b: b.reading_order if b.reading_order is not None else 10**6,
        )
        for block in ordered:
            lines.extend(ln for ln in block.text.splitlines() if ln.strip())
    KEY_LINES_OUT.write_text("\n".join(lines), encoding="utf-8")
    return lines


def _promotion_before_after_live_p66(pdf: bytes) -> dict:
    """Promotion delta on PPSC-66 with ONE OCR pass: extract +
    resolve once, then match twice (promotion off vs on). The
    delta is purely the promotion — no OCR variance between the
    two arms."""
    from app.config import Settings
    from app.pipeline.answers.service import apply_resolution
    from app.pipeline.extract.service import extract_from_ocr_blocks
    from app.pipeline.interfaces import PageContext
    from app.pipeline.layout.analyzer import GeometryLayoutAnalyzer
    from app.pipeline.matching import match_document
    from app.pipeline.matching.promotion import promote_pending
    from app.pipeline.matching.service import resolve_with_key_detection
    from app.pipeline.ocr.psm import select_psm
    from app.pipeline.ocr.tesseract import TesseractAdapter
    from app.pipeline.pdf.quality import measure_quality, png_to_gray
    from app.pipeline.pdf.renderer import render_pdf_page

    settings = Settings()
    analyzer = GeometryLayoutAnalyzer()
    all_blocks: list = []
    lines: list[str] = []
    for page_number in range(1, 8):
        rendered = render_pdf_page(pdf, page_number, dpi=200)
        quality = measure_quality(png_to_gray(rendered.png_bytes))
        adapter = TesseractAdapter(languages=settings.tesseract_languages, psm=select_psm(quality))
        context = PageContext(
            document_id=uuid.uuid4(),
            page_number=page_number,
            storage_path="",
            classification="scanned",
            image_png=rendered.png_bytes,
        )
        blocks = adapter.recognize(context)
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
        for block in ordered:
            lines.extend(ln for ln in block.text.splitlines() if ln.strip())
    result = extract_from_ocr_blocks(all_blocks, "m6-ppsc66-promo")
    resolution, _ = resolve_with_key_detection(result, lines, "m6-ppsc66-promo")
    apply_resolution(result, resolution)
    import copy

    before_result = copy.deepcopy(result)
    before = match_document(before_result, resolution)
    promotion_report = promote_pending(result, resolution)
    after = match_document(
        result,
        resolution,
        promoted_numbers=set(promotion_report.promoted),
        promotion_report=promotion_report,
    )
    return {
        "before": {
            "answered": before.answered,
            "unknown": before.unknown,
            "pending": len(before.pending),
            "questions": len(before.questions),
        },
        "after": {
            "answered": after.answered,
            "unknown": after.unknown,
            "pending": len(after.pending),
            "questions": len(after.questions),
        },
        "promoted": after.promotion.get("promoted", []),
        "promoted_count": after.promotion.get("promoted_count", 0),
        "skipped": after.promotion.get("skipped", []),
    }


def _key_region_before_after() -> dict:
    """Whole-blob key parse (M5 way) vs region-located parse (M6),
    on the SAME live OCR lines. Scored against the Gemini key GT."""
    from app.pipeline.answers.key_detector import detect_trailing_key
    from app.pipeline.extract.keys import resolve_answer_token
    from app.pipeline.extract.models import ExtractedQuestion
    from app.pipeline.matching.key_region import parse_key_entries_in_region

    lines = _live_p66_key_lines()
    key_gt = _ppsc66_key_gt()
    questions = [
        ExtractedQuestion(number=n, text=f"Q{n}?", options=["A", "B", "C", "D"], correct_index=-1)
        for n in range(1, 101)
    ]

    def _score_detection(detection) -> dict:
        tp = sum(
            1
            for e in detection.applied
            if resolve_answer_token(key_gt.get(e.question_number, ""), ["A", "B", "C", "D"])
            == e.correct_index
        )
        return {
            "entries_parsed": len(detection.entries_parsed),
            "applied": len(detection.applied),
            "prf_vs_gt_key": _prf(tp, len(detection.applied) - tp, len(key_gt) - tp),
        }

    whole = detect_trailing_key(
        "\n".join(lines),
        questions=questions,
        paper_identity={"paper_number": "66", "paper_title": "Paper 66"},
        source_document_id="m6-benchmark",
        key_is_bare=True,
        single_paper_in_document=True,
    )
    entries, region = parse_key_entries_in_region(lines)
    region_detection = detect_trailing_key(
        region.region_text,
        questions=questions,
        paper_identity={"paper_number": "66", "paper_title": "Paper 66"},
        source_document_id="m6-benchmark",
        key_is_bare=True,
        single_paper_in_document=True,
    )
    return {
        "live_lines": len(lines),
        "before_whole_blob": _score_detection(whole),
        "after_region_located": {
            **_score_detection(region_detection),
            "region": region.to_dict(),
            "entries_in_region": len(entries),
        },
    }


def _paper60_stem(text: str, number: int) -> str:
    """The question stem for ``number`` from the Gemini reference
    text: the block starting at ``"<number>. "`` up to the first
    option marker ``(A)``/``(B)``/..., whitespace-normalised.
    ``_paper60_questions`` (M5) keeps options + starred only, so
    the stem has to come from the raw reference; ``_score_mcq``
    pairs by number AND stem similarity (>= 0.85), and an empty
    stem would match nothing."""
    match = re.search(rf"(?m)^{number}\.\s(.*?)(?=^\d+\.\s|\Z)", text, re.S)
    if match is None:
        return ""
    block = match.group(1)
    stem = re.split(r"\([A-D]\)", block, maxsplit=1)[0]
    return re.sub(r"\s+", " ", stem).strip()


def _paper60_live() -> dict:
    """End-to-end Paper 60 photo: Tesseract OCR -> extract ->
    style-star evidences -> resolve -> promote -> match, scored
    against the Gemini-reference GT (starred option = answer)."""
    from app.pipeline.answers.service import (
        apply_resolution,
        resolve_document_answers,
    )
    from app.pipeline.answers.style_detector import detect_style_marks
    from app.pipeline.extract.service import extract_from_ocr_blocks
    from app.pipeline.interfaces import PageContext
    from app.pipeline.matching import match_document
    from app.pipeline.matching.promotion import promote_pending
    from app.pipeline.ocr.tesseract import TesseractAdapter

    start = time.monotonic()
    photo = (PPSC66_DIR / "paper60-photo.jpg").read_bytes()
    gemini_text = (PPSC66_DIR / "paper60_gemini_ocr.txt").read_text()
    gt_questions = _paper60_questions(gemini_text)
    gt = [
        {
            "number": q["number"],
            "text": _paper60_stem(gemini_text, q["number"]),
            "options": q["options"],
            "answer": chr(65 + q["starred"]) if q["starred"] >= 0 else None,
        }
        for q in gt_questions
    ]
    adapter = TesseractAdapter(languages="eng+urd", psm=3)
    context = PageContext(
        document_id=uuid.uuid4(),
        page_number=1,
        storage_path="",
        classification="scanned",
        image_png=photo,
    )
    blocks = adapter.recognize(context)
    result = extract_from_ocr_blocks(blocks, "m6-paper60")
    evidences = []
    for question in list(result.questions) + list(result.pending):
        if len(question.options) == 4:
            evidences.extend(
                detect_style_marks(question.number, list(question.options), is_ocr=True)
            )
    resolution = resolve_document_answers(result, evidences)
    apply_resolution(result, resolution)
    promotion_report = promote_pending(result, resolution)
    matched = match_document(
        result,
        resolution,
        promoted_numbers=set(promotion_report.promoted),
        promotion_report=promotion_report,
    )
    detected = [q.to_dict() for q in matched.questions]
    score = _score_mcq(detected, gt, score_answers=True)
    return {
        "seconds": round(time.monotonic() - start, 1),
        "questions": len(matched.questions),
        "pending": len(matched.pending),
        "answered": matched.answered,
        "promotion": matched.promotion,
        "score": score,
        "gt_questions": len(gt),
        "gt_with_star_answer": sum(1 for g in gt if g["answer"]),
    }


def _psm_page_table() -> dict:
    path = PSM_EXPERIMENT if PSM_EXPERIMENT.exists() else PSM_EXPERIMENT_TMP
    if not path.exists():
        return {"status": "UNVERIFIED — m6-psm-experiment.json not found"}
    data = json.loads(path.read_text())
    out: dict = {}
    for page, v in data["pages"].items():
        out[f"p{page}"] = {
            "quality": v["quality"],
            "psm3": v["variants"]["psm3"],
            "psm4": v["variants"]["psm4"],
        }
    return out


def main() -> None:
    # The benchmark MEASURES calibration; it must never consume a
    # previous run's fit. A stale m6-calibration.json on disk is
    # loaded by parse_document_bytes (load_calibration) and would
    # silently recalibrate every confidence before the points are
    # even collected (M6 run 3: points came out at mean confidence
    # 0.392 from the run-2 fit). Delete it first; the run rewrites
    # it at the end from this run's own points.
    if CAL_OUT.exists():
        CAL_OUT.unlink()
        print("== removed stale docs/benchmarks/m6-calibration.json ==")
    report: dict = {
        "milestone": "M6",
        "date": "2026-11-22",
        "vm": "VM numbers — NOT Render numbers",
        "peak_rss_mb": _peak_rss_mb(),
    }
    all_points: list[tuple[float, bool]] = []

    print("== M6: end-to-end digital fixtures ==")
    report["end_to_end"] = {}
    gt_testpoint, _ = _load_testpoint()
    r, pts = _end_to_end_digital(
        "English_1000_Most_Repeated_MCQs_by_TestPoint.pk.pdf",
        gt_testpoint,
        score_answers=True,
        source_id="m6-testpoint",
    )
    report["end_to_end"]["testpoint"] = r
    all_points.extend(pts)
    print(f"  testpoint: {r['counts']} score={r['score']['question_detection']}")
    gt_computer, _ = _load_computer()
    pdf = (PPSC66_DIR / "Computer_Past_Papers_2019-2025.pdf").read_bytes()
    start = time.monotonic()
    matched, _, _ = parse_document_bytes(pdf, "m6-computer")
    qa_detected = [
        {"number": q.number, "text": q.text, "options": [], "answer": q.answer_text}
        for q in matched.qa_pairs
    ]
    report["end_to_end"]["computer_qa"] = {
        "seconds": round(time.monotonic() - start, 1),
        "qa_pairs": len(matched.qa_pairs),
        "score": _score_qa(qa_detected, gt_computer),
    }
    print(f"  computer qa: {report['end_to_end']['computer_qa']['score']}")
    gt_ca40, _ = _load_ca40()
    r, pts = _end_to_end_digital(
        "ppsc-current-affairs-40-mcqs.pdf",
        gt_ca40,
        score_answers=True,
        source_id="m6-ca40",
    )
    report["end_to_end"]["ca40"] = r
    all_points.extend(pts)
    print(f"  ca40: {r['counts']} score={r['score']['question_detection']}")
    gt_urdu, _ = _load_urdu_noa()
    r, pts = _end_to_end_digital(
        "PDF_Urdu_MCQs_NOA.pdf",
        gt_urdu,
        score_answers=True,
        source_id="m6-urdu-noa",
    )
    report["end_to_end"]["urdu_noa"] = r
    all_points.extend(pts)
    print(f"  urdu_noa: {r['counts']} score={r['score']['question_detection']}")

    print("== M6: promotion before/after (digital) ==")
    report["promotion_before_after"] = {}
    pdf = (PPSC66_DIR / "English_1000_Most_Repeated_MCQs_by_TestPoint.pk.pdf").read_bytes()
    report["promotion_before_after"]["testpoint"] = _promotion_before_after(
        pdf, "m6-testpoint-promo"
    )
    print(
        f"  testpoint: {report['promotion_before_after']['testpoint']['before']} -> "
        f"{report['promotion_before_after']['testpoint']['after']}"
    )
    pdf = (PPSC66_DIR / "ppsc-current-affairs-40-mcqs.pdf").read_bytes()
    report["promotion_before_after"]["ca40"] = _promotion_before_after(pdf, "m6-ca40-promo")
    print(
        f"  ca40: {report['promotion_before_after']['ca40']['before']} -> "
        f"{report['promotion_before_after']['ca40']['after']}"
    )

    print("== M6: PPSC-66 live (routed vs unrouted PSM) ==")
    p66_pdf = (FLUTTER_FIX / "ppsc_paper_66.pdf").read_bytes()
    start = time.monotonic()
    routed, _, routed_debug = parse_document_bytes(p66_pdf, "m6-ppsc66")
    routed_seconds = round(time.monotonic() - start, 1)
    start = time.monotonic()
    unrouted, _, unrouted_debug = parse_document_bytes(
        p66_pdf, "m6-ppsc66-unrouted", psm_override=3
    )
    unrouted_seconds = round(time.monotonic() - start, 1)
    key_gt = _ppsc66_key_gt()

    # The GT values are full entry texts ("(B) Broke out") — the
    # calibration needs the single answer letter. Entries with no
    # extractable letter get answer None and are excluded from
    # the points (never guessed). (M6 run 2/3 built "answer": v
    # with the full text, so _gt_answer_index returned None for
    # every live entry and the live points were silently 0.)
    def _key_letter(entry_text: str) -> str | None:
        match = re.search(r"\(([A-D])\)", entry_text)
        return match.group(1) if match else None

    key_gt_list = [
        {"number": n, "text": "", "options": ["", "", "", ""], "answer": _key_letter(v)}
        for n, v in sorted(key_gt.items())
    ]
    # Answer correctness on the recovered numbers only (GT key
    # letters, matched by number).
    routed_points = _calibration_points(
        [q.to_dict() for q in routed.questions], key_gt_list, by_number=True
    )
    report["ppsc66_live"] = {
        "routed_select_psm": {
            "seconds": routed_seconds,
            "psm_by_page": routed_debug["psm_by_page"],
            "counts": routed.counts,
            "answered": routed.answered,
            "unknown": routed.unknown,
            "pending": len(routed.pending),
            "promotion": routed.promotion,
            "validation_issues": len(routed.validation_issues),
            "recovered_of_100": len(
                {
                    q.number
                    for q in list(routed.questions)
                    if q.number is not None and 1 <= q.number <= 100
                }
            ),
        },
        "unrouted_psm3_everywhere": {
            "seconds": unrouted_seconds,
            "psm_by_page": unrouted_debug["psm_by_page"],
            "counts": unrouted.counts,
            "answered": unrouted.answered,
            "unknown": unrouted.unknown,
            "pending": len(unrouted.pending),
            "recovered_of_100": len(
                {
                    q.number
                    for q in list(unrouted.questions)
                    if q.number is not None and 1 <= q.number <= 100
                }
            ),
        },
    }
    print(f"  routed: {report['ppsc66_live']['routed_select_psm']}")
    print(f"  unrouted: {report['ppsc66_live']['unrouted_psm3_everywhere']}")
    report["promotion_before_after"]["ppsc66_live"] = _promotion_before_after_live_p66(p66_pdf)
    print(
        f"  ppsc66 promotion: "
        f"{report['promotion_before_after']['ppsc66_live']['before']} -> "
        f"{report['promotion_before_after']['ppsc66_live']['after']}"
    )

    print("== M6: key-region before/after (live key) ==")
    report["key_region_before_after"] = _key_region_before_after()
    print(f"  whole-blob: {report['key_region_before_after']['before_whole_blob']}")
    print(f"  region: {report['key_region_before_after']['after_region_located']}")

    print("== M6: Paper 60 live ==")
    report["paper60_live"] = _paper60_live()
    print(f"  paper60: {report['paper60_live']['score']}")

    print("== M6: calibration ==")
    # Points already collected from the digital end-to-end runs
    # above; add the PPSC-66 live points (GT key letters).
    all_points.extend(routed_points)
    fit = fit_calibration(all_points)
    CAL_OUT.write_text(json.dumps(fit.to_dict(), indent=1, ensure_ascii=False))
    report["calibration"] = fit.to_dict()
    report["calibration"]["total_pairs"] = len(all_points)
    print(f"  pairs={len(all_points)} ece_before={fit.ece_before} ece_after={fit.ece_after}")
    for b in fit.buckets:
        print(
            f"    {b.label}: n={b.n} mean_conf={b.mean_confidence} "
            f"acc={b.accuracy} calibrated={b.calibrated_confidence}"
        )

    print("== M6: PSM page experiment ==")
    report["ppsc66_psm_page_experiment"] = _psm_page_table()
    tp = report["end_to_end"]["testpoint"]["score"]["question_detection"]
    report["testpoint_residual"] = {
        "question_fp": tp["fp"],
        "question_prf": tp,
        "note": "M5 residual was 28 FPs; M6 did not change extraction.",
    }
    print(f"  testpoint FP: {tp['fp']} (M5: 28)")
    report["peak_rss_mb"] = _peak_rss_mb()
    OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"\nwrote {OUT}")
    print(f"wrote {CAL_OUT}")
    print(f"peak RSS: {report['peak_rss_mb']} MB (VM)")


if __name__ == "__main__":
    main()
