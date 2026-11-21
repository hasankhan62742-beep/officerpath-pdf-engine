# OfficerPath AI — PDF Engine (Phase 1, M2) — tests
# PDF analysis, real per-page classification, bounded rendering,
# and quality metrics — on generated fixtures + the real PPSC-66 pages.
# No OCR here: these tests measure what is IN the file, not what text
# an OCR engine would read (that is M3).

from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
import pytest

from app.config import Settings
from app.pipeline.ingestion.classifier import classify_pages
from app.pipeline.ingestion.validator import validate_file
from app.pipeline.pdf.analysis import analyze_pdf
from app.pipeline.pdf.classifier import classify_pages_from_analysis
from app.pipeline.pdf.quality import estimate_skew, measure_quality, png_to_gray
from app.pipeline.pdf.renderer import render_image_file, render_pdf_page

FIXTURES = Path(__file__).parent / "fixtures" / "m2"
PPSC66 = Path(__file__).parent / "fixtures" / "ppsc66"


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_analyze_clean_pdf_is_digital():
    analysis = analyze_pdf(_read("clean.pdf"))
    assert analysis.page_count == 2
    assert analysis.encrypted is False
    page1 = analysis.pages[0]
    assert page1.text_char_count > 100
    assert page1.text_span_count > 0
    assert page1.image_count == 0
    assert page1.image_coverage == 0.0
    assert page1.has_text_layer is True
    assert page1.rotation_degrees == 0
    assert page1.fonts  # font metadata is recorded, not guessed


def test_analyze_scanned_pdf_has_no_text_layer():
    analysis = analyze_pdf(_read("scanned.pdf"))
    assert analysis.page_count == 1
    page = analysis.pages[0]
    assert page.text_char_count == 0
    assert page.has_text_layer is False
    assert page.image_count == 1
    assert page.image_coverage > 0.9


def test_analyze_mixed_pdf_is_per_page():
    analysis = analyze_pdf(_read("mixed.pdf"))
    assert analysis.page_count == 2
    assert analysis.pages[0].has_text_layer is True
    assert analysis.pages[1].has_text_layer is False
    assert analysis.pages[1].image_count == 1


def test_analyze_blank_pdf():
    analysis = analyze_pdf(_read("blank.pdf"))
    page = analysis.pages[0]
    assert page.text_char_count == 0
    assert page.image_count == 0
    assert page.drawing_count == 0


def test_analyze_corrupt_pdf_raises():
    with pytest.raises(ValueError):
        analyze_pdf(b"this is not a pdf at all")


def test_analyze_encrypted_pdf_raises_and_is_never_bypassed(tmp_path):
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    page = doc[0]
    page.insert_text((72, 72), "secret", fontsize=11)
    path = tmp_path / "enc.pdf"
    doc.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    doc.close()
    with pytest.raises(ValueError, match="encrypted"):
        analyze_pdf(path.read_bytes())


def test_classify_fixtures_from_real_evidence():
    expected = {
        "clean.pdf": ["digital", "digital"],
        "scanned.pdf": ["scanned"],
        "mixed.pdf": ["digital", "scanned"],
        "blank.pdf": ["blank"],
        "low_contrast.pdf": ["digital"],
        "noisy.pdf": ["scanned"],
        "skewed.pdf": ["scanned"],
    }
    for name, labels in expected.items():
        pages = classify_pages_from_analysis(analyze_pdf(_read(name)).pages)
        assert [p.classification for p in pages] == labels, name
        assert all(p.method == "pymupdf-evidence" for p in pages)


def test_m1_classifier_now_uses_real_evidence_when_bytes_given():
    data = _read("scanned.pdf")
    report = validate_file("scanned.pdf", data, Settings())
    assert report.valid
    # With bytes: exact classification (the M1 byte heuristic said
    # "unknown" for this file — compressed streams hid the markers).
    pages = classify_pages(report, data=data)
    assert pages[0].classification == "scanned"
    assert pages[0].method == "pymupdf-evidence"
    # Without bytes: the old heuristic fallback still works.
    pages_fallback = classify_pages(report)
    assert pages_fallback[0].classification in ("scanned", "unknown")


def test_render_clean_page_bounded_dpi():
    rendered = render_pdf_page(_read("clean.pdf"), 1, dpi=200)
    assert rendered.width_px == 1653
    assert rendered.height_px == 2339
    assert rendered.dpi_used == 200.0
    assert rendered.png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_huge_dpi_is_bounded_down():
    rendered = render_pdf_page(_read("clean.pdf"), 1, dpi=2000, max_pixels=12_000_000)
    assert rendered.dpi_used < 2000
    assert rendered.width_px * rendered.height_px <= 12_000_000


def test_render_page_out_of_range_raises():
    with pytest.raises(ValueError):
        render_pdf_page(_read("clean.pdf"), 99, dpi=200)


def test_render_image_file_ppsc66():
    data = (PPSC66 / "p-1.png").read_bytes()
    rendered = render_image_file(data, dpi=200)
    assert rendered.width_px == 1105
    assert rendered.height_px == 1430
    assert rendered.source == "pillow"


def test_quality_clean_vs_low_contrast():
    clean = measure_quality(png_to_gray(render_pdf_page(_read("clean.pdf"), 1).png_bytes))
    faint = measure_quality(png_to_gray(render_pdf_page(_read("low_contrast.pdf"), 1).png_bytes))
    assert clean.blur_score is not None and clean.blur_score > 100
    assert clean.contrast_score is not None and clean.contrast_score > 20
    assert faint.contrast_score is not None and faint.contrast_score < 15
    assert faint.blur_score is not None and faint.blur_score < clean.blur_score


def test_quality_skew_measured_on_skewed_fixture():
    skewed = measure_quality(png_to_gray(render_pdf_page(_read("skewed.pdf"), 1).png_bytes))
    assert skewed.skew_degrees is not None
    assert 4.0 <= abs(skewed.skew_degrees) <= 6.0


def test_quality_blank_page_has_no_skew_and_no_ink():
    blank = measure_quality(png_to_gray(render_pdf_page(_read("blank.pdf"), 1).png_bytes))
    assert blank.skew_degrees is None
    assert blank.ink_coverage == 0.0
    assert blank.blur_score == 0.0
    assert blank.bleed_through is None  # honestly not measured (no reference)


def test_estimate_skew_on_blank_array_is_none():
    assert estimate_skew(np.full((400, 400), 255, dtype=np.uint8)) is None


def test_ppsc66_pages_are_all_scanned_images():
    for n in range(1, 8):
        data = (PPSC66 / f"p-{n}.png").read_bytes()
        rendered = render_image_file(data, dpi=200)
        gray = png_to_gray(rendered.png_bytes)
        quality = measure_quality(gray)
        assert quality.ink_coverage is not None and quality.ink_coverage > 0.005
        assert quality.blur_score is not None and quality.blur_score > 0
