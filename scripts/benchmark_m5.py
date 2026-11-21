# OfficerPath AI — M5 benchmark (2026-11-21).
#
# Measures the M5 answer detectors (app/pipeline/answers/) per
# detector on the golden set, plus the M4 follow-ups:
# - TestPoint residual FPs after the positional consumption pass
#   (M4: 248 FPs, Q P/R/F1 0.8472/1.0/0.9173).
# - PPSC-66 end-to-end live-Tesseract recovery after the PSM
#   experiment (M4: 41/100 on the psm3-layout path).
#
# ALL numbers are measured in this run, on THIS VM (labelled VM
# numbers — NOT Render numbers). Anything unmeasured is reported
# as UNVERIFIED. No PaddleOCR (ADR-005). No Gemini API calls; the
# stored Gemini reference texts are used as ground truth for the
# PPSC-66 key and the Paper 60 stars, where noted. The live
# PPSC-66 run re-uses the M5 full-run experiment's saved lines
# when present (/tmp/m5-full/lines_*.txt) and re-runs the
# psm3-layout path live when they are absent.
#
# Usage: .venv/bin/python scripts/benchmark_m5.py
# Output: docs/benchmarks/m5-benchmark-2026-11-21.json + stdout summary.

from __future__ import annotations

import json
import re
import resource
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from benchmark_m4 import (  # noqa: E402
    _detected_as_dicts,
    _load_computer,
    _load_testpoint,
    _prf,
    _run_digital_pdf,
    _score_mcq,
)

from app.pipeline.answers.handwriting import (  # noqa: E402
    classify_ink_region,
    find_unmatched_ink,
)
from app.pipeline.answers.inline_detector import (  # noqa: E402
    check_monthly_ca_answers,
    detect_inline_answer,
    detect_qa_answer,
)
from app.pipeline.answers.key_detector import detect_trailing_key  # noqa: E402
from app.pipeline.answers.service import (  # noqa: E402
    apply_resolution,
    resolve_document_answers,
)
from app.pipeline.answers.style_detector import (  # noqa: E402
    detect_bold_option,
    detect_star_option,
)
from app.pipeline.answers.visual_detector import (  # noqa: E402
    detect_marks_in_image,
    option_boxes_from_tesseract,
)
from app.pipeline.extract.keys import parse_key_entries  # noqa: E402
from app.pipeline.extract.tables import parse_sr_pdfplumber_tables  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "app/tests/fixtures/golden/ppsc66"
PPSC66_DIR = Path.home() / "workspace/officerpath-ai/test-fixtures/ppsc66"
OUT = ROOT / "docs/benchmarks/m5-benchmark-2026-11-21.json"
M4_JSON = ROOT / "docs/benchmarks/m4-benchmark-2026-11-21.json"
PSM_EXPERIMENT = Path("/tmp/m5-psm-experiment.json")
FULL_EXPERIMENT = Path("/tmp/m5-full-experiment.json")


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


# ------------------------------------------------------------------
# Ground truth builders.
# ------------------------------------------------------------------


def _ppsc66_key_gt() -> dict[int, str]:
    """The PPSC-66 trailing key, 1–100, from the stored Gemini
    reference: p6 lines 36–121 (entries 1–78) + p7 lines 1–42
    (entries 79–100). The key is SPLIT across the two pages and
    the p6 explanation items (lines 16–35) must not be read as
    key entries — the slice starts after them."""
    p6 = (FIX / "ocr-p6.txt").read_text().splitlines()
    p7 = (FIX / "ocr-p7.txt").read_text().splitlines()
    return parse_key_entries("\n".join(p6[35:]) + "\n" + "\n".join(p7[:42]))


def _paper60_questions(text: str) -> list[dict]:
    """Parse the Paper 60 Gemini reference (or live Tesseract
    text) into questions with options. Wrapped option lines are
    joined first: a star can sit at the end of a continuation
    line ("application*"), not on the marker line. Returns
    [{number, options, starred}] with starred = the starred
    option index or -1. Questions after 21 have empty options in
    the reference and are dropped (unanswerable from the text)."""
    section = text.split("PAPER 60", 1)[1] if "PAPER 60" in text else text
    # Join wrapped lines: a line that does not start a new
    # question/option continues the previous line.
    joined: list[str] = []
    for line in section.splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        if re.match(r"^\d+\.\s", line) or re.match(r"^\([A-D]\)", line):
            joined.append(line)
        elif joined:
            joined[-1] = joined[-1] + " " + line.strip()
    questions: list[dict] = []
    current: dict | None = None

    def _add_option(line_text: str) -> None:
        # A line can carry MULTIPLE inline options ("(A) ISDN (B)
        # Modem" — the live OCR merges columns). Split on every
        # option marker, not just the first.
        nonlocal current
        if current is None:
            return
        segments = re.split(r"(?=\([A-D]\)\s)", line_text)
        for segment in segments:
            option_match = re.match(r"^\(([A-D])\)\s*(.*)$", segment.strip())
            if not option_match:
                continue
            text_value = option_match.group(2)
            starred = text_value.rstrip().endswith("*")
            # The star STAYS in the option text: the style detector
            # reads the raw option text, markers included. (An
            # earlier version of this parser stripped it, which made
            # the detector score 0/20 — a parser bug, not a detector
            # result.)
            current["options"].append(text_value.strip())
            if starred:
                current["starred"] = len(current["options"]) - 1

    for line in joined:
        number_match = re.match(r"^(\d+)\.\s+(.*)$", line)
        if number_match:
            if current is not None:
                questions.append(current)
            current = {
                "number": int(number_match.group(1)),
                "options": [],
                "starred": -1,
            }
            # The stem may carry the first option inline; the
            # option splitter handles it.
            _add_option(number_match.group(2))
            continue
        if re.match(r"^\([A-D]\)", line):
            _add_option(line)
    if current is not None:
        questions.append(current)
    # Keep only questions with >= 3 non-empty options (Q1–Q20 in
    # the reference; Q21+ have empty options and no answer in the
    # text, so they are unanswerable from it).
    return [
        q
        for q in questions
        if len(q["options"]) == 4 and sum(1 for o in q["options"] if o.strip()) >= 3
    ]


# ------------------------------------------------------------------
# Per-detector measurements.
# ------------------------------------------------------------------


def _measure_key_detector() -> dict:
    key_gt = _ppsc66_key_gt()
    assert len(key_gt) == 100, f"key GT must be 100 entries, got {len(key_gt)}"
    # (a) Ideal text: a clean reconstruction of the key — one
    # "N. (L)" line per entry, letter only. (An earlier version
    # interpolated the full GT value "(B) Broke out" into "(v)",
    # producing "1. ((B) Broke out)" — a harness bug that made the
    # detector score 0/100.)
    from app.pipeline.extract.keys import resolve_answer_token

    key_text = "\n".join(
        f"{n}. ({chr(65 + resolve_answer_token(v, ['A', 'B', 'C', 'D']))})"
        for n, v in sorted(key_gt.items())
    )
    from app.pipeline.extract.models import ExtractedQuestion

    questions = [
        ExtractedQuestion(
            number=n,
            text=f"Question {n}?",
            options=["A", "B", "C", "D"],
            paper_identity={"paper_number": "66", "paper_title": "Paper 66"},
        )
        for n in range(1, 101)
    ]
    ideal = detect_trailing_key(
        key_text,
        questions=questions,
        paper_identity={"paper_number": "66", "paper_title": "Paper 66"},
        source_document_id="ppsc66",
        key_is_bare=False,
        single_paper_in_document=True,
    )
    # parse_key_entries values are the full remainder ("(B) Broke
    # out"), so the GT letter comes from resolve_answer_token, not
    # from a string comparison with "(B)".
    tp = sum(
        1
        for e in ideal.applied
        if resolve_answer_token(key_gt.get(e.question_number, ""), ["A", "B", "C", "D"])
        == e.correct_index
    )
    fp = len(ideal.applied) - tp
    fn = len(key_gt) - tp
    return {
        "ground_truth_entries": len(key_gt),
        "ideal_text": {
            "entries_parsed": len(ideal.entries_parsed),
            "applied": len(ideal.applied),
            "filtered": len(ideal.filtered),
            "unmatched": ideal.unmatched,
            "decision": ideal.decision,
            "prf": _prf(tp, fp, fn),
        },
    }


def _measure_inline_detector() -> dict:
    # TestPoint Ans column: the pdfplumber row dict carries the
    # Ans column already resolved as correct_index (there is no
    # raw "ans" key — the table parser resolves it). The token
    # fed to the M5 detector is that letter, so this measures
    # whether the detector re-resolves the Ans column to the same
    # index on all 1,375 rows, scored against the GT letter. The
    # end-to-end answer correctness is in the TestPoint-after
    # metrics (the extractor's own key join).
    gt, _meta = _load_testpoint()
    pdf = (FIX / "English_1000_Most_Repeated_MCQs_by_TestPoint.pk.pdf").read_bytes()
    rows = parse_sr_pdfplumber_tables(pdf)
    gt_by_sr: dict[tuple[int, int], dict] = {}
    for g in gt:
        gt_by_sr.setdefault((g["page"], g["number"]), g)
    tp = fp = fn = 0
    for row in rows:
        g = gt_by_sr.get((row["page"], row.get("number")))
        if g is None:
            continue
        correct_index = row.get("correct_index", -1)
        ans_letter = chr(65 + correct_index) if correct_index >= 0 else None
        evidence = detect_inline_answer(row.get("number"), row.get("options", []), ans_letter)
        if evidence is None or evidence.correct_index < 0:
            if g.get("answer"):
                fn += 1
            continue
        letter = chr(65 + evidence.correct_index)
        if letter == g.get("answer"):
            tp += 1
        else:
            fp += 1
    # Computer Q&A: the answer text after the question. Four GT
    # pairs have an EMPTY answer (nos. 8, 61, 396, 869) — the GT
    # itself is unanswerable there, so they are excluded from the
    # denominator, not counted as detector failures.
    gt_qa, _meta = _load_computer()
    tp_qa = fp_qa = fn_qa = gt_empty = 0
    for g in gt_qa:
        if not (g.get("answer") or "").strip():
            gt_empty += 1
            continue
        evidence = detect_qa_answer(g["number"], g["text"], g.get("answer", ""))
        if evidence is None:
            fn_qa += 1
        elif _norm(evidence.answer_text or "") == _norm(g.get("answer", "")):
            tp_qa += 1
        else:
            fp_qa += 1
    # Monthly CA: the span check on all 5 files (image OCR sample
    # included — this is the benchmark, not the unit test).
    monthly: dict = {}
    monthly_pdfs = [
        "Current-Affairs-March-2025-in-PDF.pdf",
        "Current-Affairs-April-2025-in-PDF-Free-Version.pdf",
        "Current-Affairs-June-2025-in-PDF__1.pdf",
        "Current-Affairs-July-2025-in-PDF.pdf",
        "Pakistan-Current-Affairs-August-2025-in-PDF.pdf",
    ]
    for name in monthly_pdfs:
        pdf_bytes = (FIX / name).read_bytes()
        check = check_monthly_ca_answers(pdf_bytes, name)
        monthly[name] = {
            "verdict": check.verdict,
            "reason": check.reason,
            "option_spans_checked": check.option_spans_checked,
            "bold_option_spans": check.bold_option_spans,
            "coloured_option_spans": check.coloured_option_spans,
            "correct_answer_lines": check.correct_answer_lines,
            "images_ocr_sampled": check.images_ocr_sampled,
            "images_with_answer_text": check.images_with_answer_text,
            "explanation_matches_exactly_one": check.explanation_matches_exactly_one,
            "questions": check.questions,
        }
    return {
        "testpoint_ans_column": {"prf": _prf(tp, fp, fn), "rows_scored": tp + fp + fn},
        "computer_qa_text": {
            "prf": _prf(tp_qa, fp_qa, fn_qa),
            "gt_answer_empty_excluded": gt_empty,
        },
        "monthly_ca": monthly,
    }


def _measure_style_star() -> dict:
    gemini_text = (FIX / "paper60_gemini_ocr.txt").read_text()
    gt_questions = _paper60_questions(gemini_text)
    gt_starred = {q["number"]: q["starred"] for q in gt_questions if q["starred"] >= 0}
    tp = fp = fn = 0
    for q in gt_questions:
        evidence = detect_star_option(q["number"], q["options"])
        if evidence is None or evidence.correct_index < 0:
            if q["starred"] >= 0:
                fn += 1
            continue
        if evidence.correct_index == q["starred"]:
            tp += 1
        else:
            fp += 1
    ideal = {"prf": _prf(tp, fp, fn), "questions": len(gt_questions), "gt_starred": len(gt_starred)}
    # Live Tesseract OCR of the photo: the questions cannot even
    # be segmented (the columns merge — the parser finds 0 usable
    # questions), so the detector has no valid input; the failure
    # is upstream (OCR + segmentation), not in the detector. The
    # measurable live number is STAR ATTRIBUTION: of the 7 `*`
    # characters Tesseract preserved, how many sit on a GT-starred
    # option's text (TP), on a GT non-starred option's text (FP),
    # or on text matching neither (unattributed — the merge broke
    # the attribution). GT stars with no `*` at all are FNs.
    live_text = Path("/tmp/m5-paper60-live-tess.txt").read_text()
    starred_texts = [_norm(q["options"][q["starred"]]) for q in gt_questions if q["starred"] >= 0]
    plain_texts = [
        _norm(o) for q in gt_questions for i, o in enumerate(q["options"]) if i != q["starred"]
    ]
    tp = fp = unattributed = 0
    for match in re.finditer(r"\*", live_text):
        line_start = live_text.rfind("\n", 0, match.start()) + 1
        segment = live_text[line_start : match.start()]
        markers = list(re.finditer(r"\(([A-D])\)", segment))
        fragment = _norm(segment[markers[-1].end() :]) if markers else _norm(segment)
        fragment = re.sub(r"[^a-z0-9 ]", " ", fragment).strip()
        fragment = " ".join(fragment.split())
        if len(fragment) >= 3 and any(fragment in s or s in fragment for s in starred_texts):
            tp += 1
        elif len(fragment) >= 5 and any(
            len(s) >= 5 and (fragment in s or s in fragment) for s in plain_texts
        ):
            # The length floor is on the MATCHED option text, not
            # the fragment: a 4-letter plain option ("HTTP") sitting
            # inside a merged fragment ("HTTP key repeatedly") is
            # not an attribution — it is an unattributed star.
            fp += 1
        else:
            unattributed += 1
    fn = len(gt_starred) - tp
    live = {
        "stars_preserved_in_live_ocr": live_text.count("*"),
        "correctly_attributed_tp": tp,
        "wrongly_attributed_fp": fp,
        "unattributed": unattributed,
        "prf": _prf(tp, fp, fn),
        "gt_starred": len(gt_starred),
        "note": "live OCR preserves only 7/20 stars and merges the "
        "columns, so most GT stars are simply absent from the text "
        "(FN). The detector cannot fix OCR; it reads what OCR "
        "gives it.",
    }
    return {"ideal_gemini_text": ideal, "live_tesseract_photo": live}


def _measure_style_bold() -> dict:
    """Synthetic bold-option PDF (fitz, DejaVu Bold for one
    option per question): 3 questions, Q3 with TWO bold options
    (ambiguous — must be rejected, never guessed)."""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    bold_font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    y = 100
    specs = [
        ("1. Which is the capital of France?", ["London", "Paris", "Rome", "Madrid"], [1]),
        (
            "2. Which planet is known as the Red Planet?",
            ["Venus", "Mars", "Jupiter", "Saturn"],
            [1],
        ),
        (
            "3. Which metal is liquid at room temperature?",
            ["Iron", "Mercury", "Copper", "Gold"],
            [0, 1],
        ),
    ]
    for stem, options, bold_idx in specs:
        page.insert_text((72, y), stem, fontname="helv", fontsize=12)
        y += 22
        for i, option in enumerate(options):
            label = f"({chr(65 + i)}) {option}"
            if i in bold_idx:
                page.insert_text(
                    (72, y),
                    label,
                    fontfile=bold_font,
                    fontname="DejaVuBold",
                    fontsize=12,
                )
            else:
                page.insert_text((72, y), label, fontname="helv", fontsize=12)
            y += 20
        y += 14
    pdf = doc.tobytes()
    # The detector reads RAW option texts (markers included): the
    # stored options have the U+E000 bold marker stripped by
    # clean_stored. The marker lives on the line entries
    # (service._apply_bold_markers appends it to bold lines from
    # the digital extractor's style["bold_lines"]), so the detector
    # runs on those lines. (Feeding it the stored options scores
    # 0/2 — a harness bug, not a detector result: the extractor
    # itself resolves bold correctly, as the manual check showed.)
    from app.pipeline.extract.service import _apply_bold_markers
    from app.pipeline.interfaces import PageContext
    from app.pipeline.ocr.digital import DigitalExtractor

    extractor = DigitalExtractor()
    context = PageContext(document_id=uuid.uuid4(), page_number=1, storage_path="", pdf_bytes=pdf)
    blocks = extractor.recognize(context)
    raw_lines = [line for line in _apply_bold_markers(blocks) if line.strip()]
    # Group raw option lines by the preceding question-number line.
    grouped: list[dict] = []
    current: dict | None = None
    for line in raw_lines:
        if re.match(r"^\d+\.\s", line):
            if current is not None:
                grouped.append(current)
            current = {"number": int(line.split(".", 1)[0]), "options": []}
            continue
        if re.match(r"^\([A-D]\)", line) and current is not None:
            current["options"].append(line)
    if current is not None:
        grouped.append(current)
    tp = fp = fn = 0
    detail = []
    expected = {1: 1, 2: 1, 3: -1}  # Q3 ambiguous -> no answer
    for q in grouped:
        evidence = detect_bold_option(q["number"], q["options"])
        want = expected.get(q["number"], -1)
        if evidence is None or evidence.correct_index < 0:
            if want >= 0:
                fn += 1
            detail.append({"q": q["number"], "detected": None, "expected": want})
            continue
        if evidence.correct_index == want:
            tp += 1
        else:
            fp += 1
        detail.append({"q": q["number"], "detected": evidence.correct_index, "expected": want})
    return {
        "prf": _prf(tp, fp, fn),
        "detail": detail,
        "questions": len(grouped),
        "raw_lines": len(raw_lines),
    }


def _measure_visual_and_handwriting() -> dict:
    # Synthetic pages (the unit-test builder, reused here).
    import io

    from PIL import Image

    from app.tests.test_answers_visual import _page as _visual_page

    png, boxes = _visual_page(marks=True)
    detections = detect_marks_in_image(png, boxes, question_number=1)
    want = {(1, "star"), (2, "tick"), (3, "circle"), (0, "underline")}
    got = {(d.option_index, d.mark_kind) for d in detections}
    visual_synthetic = {
        "expected_marks": len(want),
        "detected": len(detections),
        "true_positives": len(want & got),
        "false_positives": len(got - want),
        "false_negatives": len(want - got),
        "prf": _prf(len(want & got), len(got - want), len(want - got)),
    }
    png_clean, boxes_clean = _visual_page(marks=False)
    clean = detect_marks_in_image(png_clean, boxes_clean, question_number=1)
    visual_synthetic["clean_page_false_positives"] = len(clean)
    # Paper 60 photo: negative control (no pen marks exist on it).
    photo = (FIX / "paper60-photo.jpg").read_bytes()
    photo_boxes = option_boxes_from_tesseract(photo)
    photo_dets = detect_marks_in_image(photo, photo_boxes)
    visual_photo = {
        "option_boxes": len(photo_boxes),
        "detections": len(photo_dets),
        "by_kind": dict(Counter(d.mark_kind for d in photo_dets)),
        "note": "negative control: the photo has printed stars and "
        "one handwritten note, but no pen tick/circle/underline — "
        "every detection here is a false positive.",
    }
    # Handwriting: synthetic marginalia vs answer-mark pages.
    from app.tests.test_answers_handwriting import _png_with_note

    note_png, word_boxes = _png_with_note()
    regions = find_unmatched_ink(note_png, word_boxes)
    classified = [classify_ink_region(r, option_boxes=word_boxes) for r in regions]
    handwriting_synthetic = {
        "regions": len(regions),
        "marginalia": sum(1 for r in classified if r.classification == "marginalia"),
        "answer_mark": sum(1 for r in classified if r.classification == "answer-mark"),
        "unknown": sum(1 for r in classified if r.classification == "unknown"),
    }
    # Paper 60 photo: the bottom note must be marginalia.
    import pytesseract

    image = Image.open(io.BytesIO(photo))
    width, height = image.size
    data = pytesseract.image_to_data(
        image, lang="eng+urd", config="--psm 3", output_type=pytesseract.Output.DICT
    )
    words = []
    for i, text in enumerate(data["text"]):
        if (text or "").strip():
            words.append(
                {
                    "bbox": {
                        "x_min": data["left"][i] / width,
                        "y_min": data["top"][i] / height,
                        "x_max": (data["left"][i] + data["width"][i]) / width,
                        "y_max": (data["top"][i] + data["height"][i]) / height,
                    }
                }
            )
    photo_regions = find_unmatched_ink(photo, words)
    bottom = [r for r in photo_regions if r.bbox["y_min"] > 0.85]
    bottom_classified = [classify_ink_region(r, option_boxes=photo_boxes) for r in bottom]
    handwriting_photo = {
        "regions": len(photo_regions),
        "bottom_regions": len(bottom),
        "bottom_classifications": dict(Counter(r.classification for r in bottom_classified)),
        "all_classifications": dict(
            Counter(
                classify_ink_region(r, option_boxes=photo_boxes).classification
                for r in photo_regions
            )
        ),
        "note": "the handwritten note ('Dot Matrix printer / impact "
        "printer', y 0.88-0.91) must classify as marginalia, never "
        "as an answer mark. The 9 answer-mark regions elsewhere "
        "are consistent with the printed stars (ink near options "
        "Tesseract did not box as words) — UNVERIFIED as "
        "handwriting, since no fixture has a verified handwritten "
        "answer mark.",
    }
    return {
        "visual_synthetic": visual_synthetic,
        "visual_photo_negative_control": visual_photo,
        "handwriting_synthetic": handwriting_synthetic,
        "handwriting_photo": handwriting_photo,
    }


# ------------------------------------------------------------------
# M4 follow-ups.
# ------------------------------------------------------------------


def _measure_testpoint_after() -> dict:
    gt, meta = _load_testpoint()
    run = _run_digital_pdf(meta["pdf"], "testpoint-english-1000")
    det, _qa = _detected_as_dicts(run["result"])
    m4 = {}
    if M4_JSON.exists():
        m4_data = json.loads(M4_JSON.read_text())
        m4 = m4_data["digital_fixtures"]["testpoint_english_1000"]["metrics"]
    return {
        "seconds": run["seconds"],
        "metrics": _score_mcq(det, gt, score_answers=True),
        "parse_counts": {
            "questions": len(run["result"].questions),
            "pending": len(run["result"].pending),
            "skipped": len(run["result"].skipped),
        },
        "m4_baseline": m4,
    }


def _measure_ppsc66_live() -> dict:
    """Re-run the psm3-layout live path (M4's path, copied from
    benchmark_m4._run_ppsc66_live) and resolve its answers with
    the M5 key detector. The PSM variant table comes from the
    saved full-run experiment."""
    from app.config import Settings
    from app.pipeline.extract.service import extract_from_ocr_blocks
    from app.pipeline.interfaces import PageContext
    from app.pipeline.layout.analyzer import GeometryLayoutAnalyzer
    from app.pipeline.ocr.tesseract import TesseractAdapter
    from app.pipeline.pdf.renderer import render_pdf_page

    settings = Settings()
    pdf = (PPSC66_DIR / "ppsc_paper_66.pdf").read_bytes()
    start = time.monotonic()
    adapter = TesseractAdapter(languages=settings.tesseract_languages, psm=settings.tesseract_psm)
    analyzer = GeometryLayoutAnalyzer()
    all_blocks: list = []
    by_page: dict[int, list] = {}
    for page_number in range(1, 8):
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
        by_page[page_number] = ordered
        all_blocks.extend(ordered)
    # The key section is the last segment of p6 + the top of p7.
    # The M4 extractor's key join handles it; here we also run the
    # M5 key detector on the live key text for the per-detector
    # measurement. ONE source_document_id for both the extraction
    # and the key call: an earlier run used a fresh uuid for the
    # extraction and "ppsc66-live" for the key, so the gate
    # correctly refused with "different source document" and the
    # live key scored 0/100 — a harness bug, not a detector
    # result.
    doc_id = str(uuid.uuid4())
    result = extract_from_ocr_blocks(all_blocks, doc_id)
    key_gt = _ppsc66_key_gt()
    # Live key text: p6+p7 OCR lines from the saved full-run
    # lines, or from the blocks just produced.
    live_key_lines: list[str] = []
    full_lines_dir = Path("/tmp/m5-full")
    if (full_lines_dir / "lines_p6_psm3-layout.txt").exists():
        live_key_lines = (full_lines_dir / "lines_p6_psm3-layout.txt").read_text().splitlines() + (
            full_lines_dir / "lines_p7_psm3-layout.txt"
        ).read_text().splitlines()
    else:
        for page_number in (6, 7):
            for block in by_page[page_number]:
                live_key_lines.extend(block.text.splitlines())
    live_key_text = "\n".join(live_key_lines)
    key_detection = detect_trailing_key(
        live_key_text,
        questions=list(result.questions) + list(result.pending),
        paper_identity={"paper_number": "66", "paper_title": "Paper 66"},
        source_document_id=doc_id,
        key_is_bare=True,
        single_paper_in_document=True,
    )
    from app.pipeline.extract.keys import resolve_answer_token

    tp = sum(
        1
        for e in key_detection.applied
        if resolve_answer_token(key_gt.get(e.question_number, ""), ["A", "B", "C", "D"])
        == e.correct_index
    )
    fp = len(key_detection.applied) - tp
    fn = len(key_gt) - tp
    # Resolve the whole document with the M5 service (M4 answers
    # as evidence + the key detector's evidences) and count newly
    # answered questions.

    key_evidences = list(key_detection.applied)
    resolution = resolve_document_answers(result, key_evidences)
    changed = apply_resolution(result, resolution)
    answered_after = sum(1 for q in result.questions if q.correct_index >= 0)
    return {
        "seconds": round(time.monotonic() - start, 1),
        "questions": len(result.questions),
        "pending": len(result.pending),
        "recovered_of_100": len(
            {
                q.number
                for q in list(result.questions) + list(result.pending)
                if q.number is not None and 1 <= q.number <= 100
            }
        ),
        "key_detector_live": {
            "entries_parsed": len(key_detection.entries_parsed),
            "applied": len(key_detection.applied),
            "filtered": [
                {"number": f["number"], "reason": f["reason"]} for f in key_detection.filtered
            ],
            "unmatched": key_detection.unmatched,
            "decision": key_detection.decision,
            "prf_vs_gt_key": _prf(tp, fp, fn),
        },
        "m5_resolution": {
            "answered_questions_after": answered_after,
            "changed_by_resolution": changed,
            "conflicts": len(resolution.conflicts),
            "unknown": resolution.unknown,
        },
    }


def _psm_variant_table() -> dict:
    if FULL_EXPERIMENT.exists():
        data = json.loads(FULL_EXPERIMENT.read_text())
        return {
            name: {
                "recovered_of_100": v.get("questions_recovered_of_100"),
                "questions": v.get("questions"),
                "pending": v.get("pending"),
                "key_entries_applied": v.get("key_entries_applied"),
                "options_complete_4_of_4": v.get("options_complete_4_of_4"),
                "unmatched_key_entries": v.get("unmatched_key_entries"),
                "total_seconds": round(v.get("total_seconds", 0), 1),
            }
            for name, v in data.items()
        }
    return {"status": "UNVERIFIED — /tmp/m5-full-experiment.json not found"}


def _psm_page_table() -> dict:
    if PSM_EXPERIMENT.exists():
        data = json.loads(PSM_EXPERIMENT.read_text())
        return {
            f"p{v['page']}_{v['variant']}": {
                "recovered_of_expected": v.get("recovered_of_expected"),
                "cer_vs_gemini": v.get("cer_vs_gemini"),
                "seconds": v.get("seconds"),
            }
            for v in data["variants"]
        }
    return {"status": "UNVERIFIED — /tmp/m5-psm-experiment.json not found"}


def main() -> None:
    report: dict = {
        "milestone": "M5",
        "date": "2026-11-21",
        "vm": "VM numbers — NOT Render numbers",
        "peak_rss_mb": _peak_rss_mb(),
    }
    print("== M5: TestPoint after positional pass ==")
    report["testpoint_after"] = _measure_testpoint_after()
    tp = report["testpoint_after"]["metrics"]["question_detection"]
    print(
        f"  Q P/R/F1 = {tp['precision']}/{tp['recall']}/{tp['f1']} (M4: 0.8472/1.0/0.9173, FP 248)"
    )
    print("== M5: key detector ==")
    report["detectors"] = {}
    report["detectors"]["trailing_key"] = _measure_key_detector()
    print("  ideal-text key P/R/F1:", report["detectors"]["trailing_key"]["ideal_text"]["prf"])
    print("== M5: inline detector ==")
    report["detectors"]["inline"] = _measure_inline_detector()
    print("  TestPoint Ans column:", report["detectors"]["inline"]["testpoint_ans_column"])
    print("  Computer Q&A:", report["detectors"]["inline"]["computer_qa_text"])
    print(
        "  monthly CA verdicts:",
        {k: v["verdict"] for k, v in report["detectors"]["inline"]["monthly_ca"].items()},
    )
    print("== M5: style detectors ==")
    report["detectors"]["style_star"] = _measure_style_star()
    print("  star ideal:", report["detectors"]["style_star"]["ideal_gemini_text"])
    print("  star live:", report["detectors"]["style_star"]["live_tesseract_photo"])
    report["detectors"]["style_bold"] = _measure_style_bold()
    print("  bold synthetic:", report["detectors"]["style_bold"])
    print("== M5: visual + handwriting ==")
    report["detectors"]["visual_handwriting"] = _measure_visual_and_handwriting()
    print("  visual synthetic:", report["detectors"]["visual_handwriting"]["visual_synthetic"])
    print(
        "  visual photo:",
        report["detectors"]["visual_handwriting"]["visual_photo_negative_control"],
    )
    print("  handwriting photo:", report["detectors"]["visual_handwriting"]["handwriting_photo"])
    print("== M5: PPSC-66 live (psm3-layout path) ==")
    report["ppsc66_live"] = _measure_ppsc66_live()
    p66 = report["ppsc66_live"]
    print(
        f"  recovered={p66['recovered_of_100']} questions={p66['questions']} "
        f"pending={p66['pending']} key_prf={p66['key_detector_live']['prf_vs_gt_key']}"
    )
    report["ppsc66_psm_variants"] = _psm_variant_table()
    report["ppsc66_psm_page_experiment"] = _psm_page_table()
    report["peak_rss_mb"] = _peak_rss_mb()
    OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"\nwrote {OUT}")
    print(f"peak RSS: {report['peak_rss_mb']} MB (VM)")


if __name__ == "__main__":
    main()
