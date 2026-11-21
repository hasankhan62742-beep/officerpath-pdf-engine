# OfficerPath AI — PDF Engine (Phase 1, M1) — tests
# Ingestion validator + per-page classifier. Pure byte-level checks;
# no network, no live Supabase, no PDF/OCR libraries (M1 honesty:
# page counts are estimates and compressed streams yield "unknown").

import struct

from app.config import Settings
from app.pipeline.ingestion.classifier import classify_pages
from app.pipeline.ingestion.validator import validate_file


def _settings(**overrides) -> Settings:
    return Settings(**overrides)


def _pdf(pages: int = 2, encrypted: bool = False, with_text: bool = True) -> bytes:
    body = b"%PDF-1.7\n"
    body += b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
    body += f"2 0 obj << /Type /Pages /Count {pages} >> endobj\n".encode()
    for n in range(3, 3 + pages):
        body += f"{n} 0 obj << /Type /Page >> endobj\n".encode()
    if encrypted:
        body += b"10 0 obj << /Encrypt 11 0 R >> endobj\n"
    if with_text:
        body += b"BT /F1 12 Tf (What is the capital?) Tj ET\n"
    body += b"%%EOF\n"
    return body


def _png(width: int = 800, height: int = 600) -> bytes:
    ihdr = struct.pack(">IIBB", width, height, 8, 2) + b"\x00\x00\x00"
    chunk = struct.pack(">I", 13) + b"IHDR" + ihdr
    crc = struct.pack(">I", 0)
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", 0)
    return b"\x89PNG\r\n\x1a\n" + chunk + crc + iend


def _jpeg(width: int = 640, height: int = 480) -> bytes:
    sof0 = (
        b"\xff\xc0"
        + struct.pack(">H", 8 + 3)
        + b"\x08"
        + struct.pack(">HH", height, width)
        + b"\x01\x01\x11\x00"
    )
    return b"\xff\xd8" + sof0 + b"\xff\xd9"


def _webp() -> bytes:
    # VP8X canvas 100x50.
    payload = b"VP8X" + struct.pack("<I", 10) + b"\x00\x00\x00\x00"
    payload += bytes([99, 0, 0, 49, 0, 0])  # w-1=99, h-1=49 (little-endian 24-bit)
    riff = b"RIFF" + struct.pack("<I", 4 + len(payload)) + b"WEBP" + payload
    return riff


class TestValidatePdf:
    def test_valid_pdf_two_pages_text(self):
        report = validate_file("paper.pdf", _pdf(), _settings())
        assert report.valid
        assert report.mime_type == "application/pdf"
        assert report.pdf_page_count_estimate == 2
        assert report.pdf_has_text_operators is True
        assert report.pdf_encrypted is False
        assert len(report.sha256) == 64

    def test_pdf_page_count_respects_limit(self):
        report = validate_file("big.pdf", _pdf(pages=5), _settings(max_pages_per_job=2))
        assert not report.valid
        assert any(i.code == "too_many_pages" for i in report.errors)

    def test_encrypted_pdf_rejected_never_bypassed(self):
        report = validate_file("locked.pdf", _pdf(encrypted=True), _settings())
        assert not report.valid
        assert report.pdf_encrypted is True
        assert any(i.code == "pdf_encrypted" for i in report.errors)

    def test_truncated_pdf_rejected(self):
        report = validate_file("cut.pdf", b"%PDF-1.7\n1 0 obj << /Type /Page >>", _settings())
        assert not report.valid
        assert any(i.code == "pdf_truncated" for i in report.errors)

    def test_magic_bytes_mismatch(self):
        report = validate_file("fake.pdf", b"hello, not a pdf", _settings())
        assert not report.valid
        assert any(i.code == "magic_bytes_mismatch" for i in report.errors)

    def test_empty_file_rejected(self):
        report = validate_file("empty.pdf", b"", _settings())
        assert not report.valid
        assert any(i.code == "empty_file" for i in report.errors)

    def test_oversize_rejected(self):
        report = validate_file("big.pdf", _pdf(), _settings(max_file_size_bytes=10))
        assert not report.valid
        assert any(i.code == "file_too_large" for i in report.errors)

    def test_unsupported_extension(self):
        report = validate_file("run.exe", b"MZ" + b"\x00" * 10, _settings())
        assert not report.valid
        assert any(i.code == "unsupported_type" for i in report.errors)


class TestValidateImages:
    def test_png_dimensions_and_dpi_absent(self):
        report = validate_file("scan.png", _png(), _settings())
        assert report.valid
        assert report.image is not None
        assert report.image.width_px == 800
        assert report.image.height_px == 600
        assert report.decompression_ratio is not None

    def test_jpeg_dimensions(self):
        report = validate_file("photo.jpg", _jpeg(), _settings())
        assert report.valid
        assert report.image is not None
        assert report.image.width_px == 640
        assert report.image.height_px == 480

    def test_webp_dimensions(self):
        report = validate_file("scan.webp", _webp(), _settings())
        assert report.valid
        assert report.image is not None
        assert report.image.width_px == 100
        assert report.image.height_px == 50

    def test_image_dimension_limit(self):
        report = validate_file("huge.png", _png(13000, 100), _settings())
        assert not report.valid
        assert any(i.code == "image_too_large" for i in report.errors)

    def test_pixel_cap_is_the_bomb_bound(self):
        # 10000x10000 = 100 MP > 25 MP cap: rejected on absolute pixels.
        report = validate_file("bomb.png", _png(10000, 10000), _settings())
        assert not report.valid
        assert any(i.code == "image_too_many_pixels" for i in report.errors)

    def test_high_ratio_is_warning_not_rejection(self):
        # Header-only stub: decoded >> file size, but pixels are small.
        # A blank page compresses like this in real life — warn, accept.
        report = validate_file("blank.png", _png(800, 600), _settings())
        assert report.valid
        assert any(i.code == "decompression_ratio_high" for i in report.warnings)

    def test_corrupt_image_unreadable(self):
        report = validate_file("bad.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 10, _settings())
        assert not report.valid
        assert any(i.code == "image_unreadable" for i in report.errors)


class TestValidateText:
    def test_txt_ok(self):
        report = validate_file("notes.txt", b"Q1. What is 2+2?\n", _settings())
        assert report.valid

    def test_txt_with_nul_rejected(self):
        report = validate_file("notes.txt", b"abc\x00def", _settings())
        assert not report.valid
        assert any(i.code == "not_plain_text" for i in report.errors)

    def test_docx_requires_word_document(self):
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("other.txt", "x")
        report = validate_file("fake.docx", buf.getvalue(), _settings())
        assert not report.valid
        assert any(i.code == "not_a_docx" for i in report.errors)


class TestClassifyPages:
    def test_image_is_one_scanned_page(self):
        report = validate_file("scan.png", _png(), _settings())
        pages = classify_pages(report)
        assert len(pages) == 1
        assert pages[0].classification == "scanned"
        assert pages[0].method == "file-type"
        assert pages[0].width_px == 800

    def test_txt_is_one_digital_page(self):
        report = validate_file("notes.txt", b"hello", _settings())
        pages = classify_pages(report)
        assert len(pages) == 1
        assert pages[0].classification == "digital"

    def test_pdf_text_only_is_digital_heuristic(self):
        report = validate_file("paper.pdf", _pdf(with_text=True), _settings())
        pages = classify_pages(report)
        assert len(pages) == 2
        assert all(p.classification == "digital" for p in pages)
        assert pages[0].method == "byte-heuristic"
        assert pages[0].confidence == 0.6

    def test_pdf_no_markers_is_unknown_not_guessed(self):
        # No text operators and no image markers: M1 must say unknown.
        data = (
            b"%PDF-1.7\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
            b"2 0 obj << /Type /Pages /Count 1 >> endobj\n"
            b"3 0 obj << /Type /Page >> endobj\n%%EOF\n"
        )
        report = validate_file("paper.pdf", data, _settings())
        pages = classify_pages(report)
        assert pages[0].classification == "unknown"
        assert pages[0].confidence is None
        assert "M2" in (pages[0].note or "")

    def test_pdf_text_and_images_is_mixed(self):
        data = _pdf() + b"/Image /XObject\n"
        report = validate_file("paper.pdf", data, _settings())
        pages = classify_pages(report)
        assert all(p.classification == "mixed" for p in pages)
