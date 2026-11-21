# OfficerPath AI — Phase 1, M3
# Digital extractor: exact text + style metadata + reading order,
# on the M2 synthetic fixtures (ground truth known).

import json
import uuid
from pathlib import Path

import pytest

from app.pipeline.interfaces import PageContext
from app.pipeline.ocr.digital import DigitalExtractor

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "m2"
GOLDEN = Path(__file__).resolve().parent / "fixtures" / "golden"


def _context(pdf_bytes: bytes, page_number: int) -> PageContext:
    return PageContext(
        document_id=uuid.uuid4(),
        page_number=page_number,
        storage_path="",
        classification="digital",
        pdf_bytes=pdf_bytes,
    )


def test_clean_page_1_matches_ground_truth():
    pdf_bytes = (FIXTURES / "clean.pdf").read_bytes()
    blocks = DigitalExtractor().recognize(_context(pdf_bytes, 1))
    text = "\n".join(block.text for block in blocks)
    dataset = json.loads((GOLDEN / "dataset.json").read_text(encoding="utf-8"))
    expected = "\n".join(dataset["entries"][0]["lines"])
    assert text == expected


def test_clean_page_2_two_column_reading_order():
    pdf_bytes = (FIXTURES / "clean.pdf").read_bytes()
    blocks = DigitalExtractor().recognize(_context(pdf_bytes, 2))
    assert [b.reading_order for b in blocks] == sorted(
        b.reading_order for b in blocks if b.reading_order is not None
    )
    first_lines = [b.text.split("\n", 1)[0] for b in blocks]
    # Q1 and Q2 (left column) come before Q3 and Q4 (right column).
    q1 = next(i for i, line in enumerate(first_lines) if line.startswith("1."))
    q3 = next(i for i, line in enumerate(first_lines) if line.startswith("3."))
    assert q1 < q3


def test_style_metadata_captured():
    pdf_bytes = (FIXTURES / "clean.pdf").read_bytes()
    blocks = DigitalExtractor().recognize(_context(pdf_bytes, 1))
    assert blocks, "expected blocks on a digital page"
    styles = [b.style for b in blocks if b.style]
    assert styles, "expected style metadata on digital blocks"
    assert any(style.get("fonts") for style in styles)
    # Digital text has NO invented confidence.
    assert all(b.confidence is None for b in blocks)
    assert all(b.engine == "digital-pymupdf" for b in blocks)


def test_scanned_page_returns_no_blocks():
    pdf_bytes = (FIXTURES / "scanned.pdf").read_bytes()
    blocks = DigitalExtractor().recognize(_context(pdf_bytes, 1))
    assert blocks == []


def test_missing_pdf_bytes_raises():
    context = PageContext(document_id=uuid.uuid4(), page_number=1, storage_path="", pdf_bytes=None)
    with pytest.raises(ValueError, match="pdf_bytes"):
        DigitalExtractor().recognize(context)


def test_page_out_of_range_raises():
    pdf_bytes = (FIXTURES / "clean.pdf").read_bytes()
    with pytest.raises(ValueError, match="out of range"):
        DigitalExtractor().recognize(_context(pdf_bytes, 99))
