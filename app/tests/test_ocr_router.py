# OfficerPath AI — Phase 1, M3
# Routing + dedup + disagreement comparison.

from app.pipeline.interfaces import BoundingBox, OCRBlock
from app.pipeline.ocr.router import compare_engines, deduplicate_blocks, route_page


def _block(text, x_min=0.1, y_min=0.1, x_max=0.9, y_max=0.2, engine="tesseract"):
    return OCRBlock(
        text=text,
        bbox=BoundingBox(x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max),
        page_number=1,
        engine=engine,
    )


def test_route_digital_is_digital_only():
    assert route_page("digital", ["digital-pymupdf", "tesseract"]) == ["digital-pymupdf"]


def test_route_scanned_prefers_paddleocr_then_tesseract():
    assert route_page("scanned", ["digital-pymupdf", "paddleocr", "tesseract"]) == ["paddleocr"]
    assert route_page("scanned", ["digital-pymupdf", "tesseract"]) == ["tesseract"]


def test_route_scanned_with_no_ocr_engine_is_empty():
    assert route_page("scanned", ["digital-pymupdf"]) == []


def test_route_mixed_runs_both():
    assert route_page("mixed", ["digital-pymupdf", "tesseract"]) == [
        "digital-pymupdf",
        "tesseract",
    ]


def test_route_blank_runs_nothing():
    assert route_page("blank", ["digital-pymupdf", "tesseract", "paddleocr"]) == []


def test_dedup_drops_duplicate_ocr_block():
    exact = [_block("Hello world", engine="digital-pymupdf")]
    ocr = [_block("Hello world", engine="tesseract"), _block("Something else", 0.1, 0.5, 0.9, 0.6)]
    kept, dropped = deduplicate_blocks(exact, ocr)
    assert len(kept) == 1 and kept[0].text == "Something else"
    assert len(dropped) == 1 and dropped[0].text == "Hello world"


def test_dedup_keeps_different_text_in_same_region():
    exact = [_block("Hello world", engine="digital-pymupdf")]
    ocr = [_block("Goodbye world", engine="tesseract")]
    kept, dropped = deduplicate_blocks(exact, ocr)
    assert len(kept) == 1 and dropped == []


def test_compare_engines_agreeing():
    a = [_block("Hello world"), _block("Second line", 0.1, 0.3, 0.9, 0.4)]
    b = [_block("Hello world"), _block("Second line", 0.1, 0.3, 0.9, 0.4)]
    report = compare_engines(a, b)
    assert report["matched_pairs"] == 2
    assert report["agreement_score"] == 1.0
    assert report["flagged_count"] == 0


def test_compare_engines_flags_disagreement():
    a = [_block("Hello world")]
    b = [_block("Completely different text here")]
    report = compare_engines(a, b)
    assert report["matched_pairs"] == 1
    assert report["agreement_score"] is not None and report["agreement_score"] < 0.8
    assert report["flagged_count"] == 1


def test_compare_engines_no_overlap_is_unmatched():
    a = [_block("Hello", 0.05, 0.1, 0.2, 0.2)]
    b = [_block("World", 0.7, 0.7, 0.9, 0.8)]
    report = compare_engines(a, b)
    assert report["matched_pairs"] == 0
    assert report["agreement_score"] is None
