# OfficerPath AI — Phase 1, M7
# Multi-pass union merge: three OCR variants (PSM 3 + layout,
# PSM 3 raw, PSM 4 raw) union-recover questions the single path
# misses (M5 measured 59/100 vs 41/100 on PPSC-66). The mode is
# OPTIONAL and never the default.

import io

import fitz
from PIL import Image, ImageDraw, ImageFont

from app.pipeline.extract.models import ExtractedQuestion, ParseResult
from app.pipeline.matching.service import (
    _merge_parse_results,
    parse_document_bytes,
    parse_image_bytes,
)

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _mcq_image_png() -> bytes:
    """A clean 2-question MCQ image with a trailing answer key
    (same fixture the image-parse tests use)."""
    font = ImageFont.truetype(FONT, 28)
    img = Image.new("RGB", (1200, 1100), "white")
    draw = ImageDraw.Draw(img)
    lines = [
        "1. What is the capital of France?",
        "(A) London",
        "(B) Paris",
        "(C) Rome",
        "(D) Berlin",
        "",
        "2. What is 2 + 2?",
        "(A) 3",
        "(B) 4",
        "(C) 5",
        "(D) 6",
        "",
        "ANSWER KEY",
        "1. (B)",
        "2. (B)",
    ]
    y = 20
    for line in lines:
        draw.text((30, y), line, fill="black", font=font)
        y += 56
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _scanned_pdf_bytes() -> bytes:
    """The same image embedded in a PDF with NO text layer, so the
    parse path treats it as scanned."""
    png = _mcq_image_png()
    doc = fitz.open()
    page = doc.new_page(width=1200, height=1100)
    page.insert_image(fitz.Rect(0, 0, 1200, 1100), pixmap=fitz.Pixmap(png))
    assert sum(len(doc[i].get_text()) for i in range(len(doc))) == 0
    return doc.tobytes()


def _question(number, text, options=None) -> ExtractedQuestion:
    return ExtractedQuestion(
        number=number, text=text, options=list(options or ["a", "b", "c", "d"])
    )


def test_merge_prefers_first_variant_and_unions_new_questions() -> None:
    base = ParseResult(questions=[_question(1, "Capital of France?")])
    raw = ParseResult(
        questions=[
            _question(1, "Capital of France?"),  # same question, recovered twice
            _question(2, "What is 2 + 2?"),  # only the raw variant sees it
        ]
    )
    merged, report = _merge_parse_results([base, raw], labels=["psm3-layout", "psm3-raw"])
    assert [q.number for q in merged.questions] == [1, 2]
    assert report["added_by_variant"] == {"psm3-raw": 1}
    assert report["merged_questions"] == 2


def test_merge_keeps_same_number_with_different_stem() -> None:
    # Multi-section safety: Q5 in section A and Q5 in section B
    # are different questions — the merge must keep both.
    base = ParseResult(questions=[_question(5, "Capital of France?")])
    other = ParseResult(questions=[_question(5, "What is 2 + 2?")])
    merged, _ = _merge_parse_results([base, other], labels=["psm3-layout", "psm3-raw"])
    assert len(merged.questions) == 2
    assert {q.text for q in merged.questions} == {"Capital of France?", "What is 2 + 2?"}


def test_merge_recomputes_gaps_from_merged_set() -> None:
    base = ParseResult(questions=[_question(1, "One?"), _question(3, "Three?")])
    other = ParseResult(questions=[_question(2, "Two?")])
    merged, _ = _merge_parse_results([base, other], labels=["psm3-layout", "psm3-raw"])
    assert merged.number_gaps == []


def test_single_path_is_the_default() -> None:
    matched, _, debug = parse_document_bytes(_scanned_pdf_bytes(), "probe-pdf")
    assert debug["multi_pass"] is False
    assert debug["merge"] is None
    assert matched.counts["questions"] == 2
    assert matched.answered == 2


def test_multi_pass_returns_same_questions_with_merge_report() -> None:
    matched, _, debug = parse_document_bytes(_scanned_pdf_bytes(), "probe-pdf", multi_pass=True)
    assert debug["multi_pass"] is True
    merge = debug["merge"]
    assert merge["mode"] == "multi-pass-union"
    assert merge["variants"] == ["psm3-layout", "psm3-raw", "psm4-raw"]
    assert merge["merged_questions"] == 2
    # Same two questions, both answered from the key — the union
    # adds nothing on this clean page (the gain shows on PPSC-66,
    # measured in the benchmark, not here).
    assert matched.counts["questions"] == 2
    assert matched.answered == 2
    assert all(q.correct_index == 1 for q in matched.questions)


# --- M14: the image path gets the same three variants. ---


def test_image_single_path_is_the_default() -> None:
    matched, _, debug = parse_image_bytes(_mcq_image_png(), "probe-image")
    assert debug["multi_pass"] is False
    assert debug["merge"] is None
    assert matched.counts["questions"] == 2
    assert matched.answered == 2


def test_image_multi_pass_runs_all_three_variants(monkeypatch) -> None:
    """The mocked OCR records every call: exactly three, in the
    PDF path's variant order (PSM 3 + layout, PSM 3 raw, PSM 4
    raw). The mock reads nothing, so the merge is empty — the
    assertion is about which variants ran, not what they found."""
    calls: list[tuple[int, bool]] = []

    def fake_ocr_page(png_bytes, page_number, settings, *, psm, use_layout, analyzer=None):
        calls.append((psm, use_layout))
        return []

    monkeypatch.setattr("app.pipeline.matching.service._ocr_page", fake_ocr_page)
    matched, _, debug = parse_image_bytes(_mcq_image_png(), "probe-image", multi_pass=True)
    assert calls == [(3, True), (3, False), (4, False)]
    assert debug["multi_pass"] is True
    merge = debug["merge"]
    assert merge["mode"] == "multi-pass-union"
    assert merge["variants"] == ["psm3-layout", "psm3-raw", "psm4-raw"]
    assert matched.counts["questions"] == 0


def test_image_multi_pass_real_ocr_matches_single_path() -> None:
    """Real Tesseract, three passes over the same clean image:
    the union adds nothing here, but both questions survive with
    the key — the mode never loses what the single path found."""
    matched, _, debug = parse_image_bytes(_mcq_image_png(), "probe-image", multi_pass=True)
    assert debug["multi_pass"] is True
    merge = debug["merge"]
    assert merge["variants"] == ["psm3-layout", "psm3-raw", "psm4-raw"]
    assert merge["merged_questions"] == 2
    assert matched.counts["questions"] == 2
    assert matched.answered == 2
    assert all(q.correct_index == 1 for q in matched.questions)
