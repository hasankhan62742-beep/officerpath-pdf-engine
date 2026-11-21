# OfficerPath AI — Phase 1, M3
# Tesseract adapter: probe + real OCR on a rendered fixture page +
# OSD rotation probe + honest unavailability.
# (Runs the system binary; ~1-2 s per page. PaddleOCR is NOT run
# in unit tests — see test_ocr_paddle.py for parse-only tests and
# scripts/benchmark_m3.py for the real PaddleOCR measurement.)

import io
import uuid
from pathlib import Path

import pytest
from PIL import Image

from app.pipeline.interfaces import PageContext
from app.pipeline.ocr.tesseract import EngineUnavailableError, TesseractAdapter, probe_tesseract

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "m2"


def _render_clean_page_1_png() -> bytes:
    from app.pipeline.pdf.renderer import render_pdf_page

    return render_pdf_page((FIXTURES / "clean.pdf").read_bytes(), 1, dpi=200).png_bytes


def _context(png_bytes: bytes) -> PageContext:
    return PageContext(
        document_id=uuid.uuid4(),
        page_number=1,
        storage_path="",
        classification="scanned",
        image_png=png_bytes,
    )


def test_probe_reports_available_with_urd():
    info = probe_tesseract("tesseract", "eng+urd")
    assert info.available is True
    assert info.version is not None
    assert "urd" in (info.languages or [])


def test_probe_missing_binary_is_unavailable():
    info = probe_tesseract("/nonexistent/tesseract", "eng+urd")
    assert info.available is False
    assert "not found" in (info.reason or "")


def test_probe_missing_language_is_unavailable():
    info = probe_tesseract("tesseract", "eng+zzz")
    assert info.available is False
    assert "zzz" in (info.reason or "")


def test_recognize_clean_page_reads_all_questions():
    adapter = TesseractAdapter(languages="eng+urd", psm=3)
    blocks = adapter.recognize(_context(_render_clean_page_1_png()))
    text = " ".join(block.text for block in blocks)
    for token in ["Pakistan", "Lahore", "Ravi", "Thar", "Hafeez"]:
        assert token in text, f"expected {token!r} in Tesseract output"
    assert all(block.engine == "tesseract" for block in blocks)
    confidences = [b.confidence for b in blocks if b.confidence is not None]
    assert confidences and all(0.0 <= c <= 1.0 for c in confidences)


def test_recognize_without_image_raises():
    adapter = TesseractAdapter()
    context = PageContext(document_id=uuid.uuid4(), page_number=1, storage_path="")
    with pytest.raises(ValueError, match="image_png"):
        adapter.recognize(context)


def test_unavailable_adapter_raises_engine_unavailable():
    adapter = TesseractAdapter(binary="/nonexistent/tesseract")
    with pytest.raises(EngineUnavailableError):
        adapter.recognize(_context(_render_clean_page_1_png()))


def test_osd_detects_upright_page():
    adapter = TesseractAdapter()
    result = adapter.detect_rotation(_render_clean_page_1_png())
    assert result is not None
    assert result["degrees"] == 0
    assert result["method"] == "tesseract-osd"


def test_osd_on_blank_image_returns_none():
    adapter = TesseractAdapter()
    image = Image.new("RGB", (100, 100), (255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    assert adapter.detect_rotation(buffer.getvalue()) is None
