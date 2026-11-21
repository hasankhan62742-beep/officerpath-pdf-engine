# OfficerPath AI — PDF Engine (Phase 1, M1)
# File validation (prompt §6): extension + magic bytes, configurable
# size/page/dimension limits, integrity (encryption reported, never
# bypassed; corruption detected), decompression-bomb guard.
#
# M1 limits, stated honestly: this validator works on raw bytes with
# the standard library only. It does NOT render pages (M2, PyMuPDF)
# and does NOT run OpenCV (M2). Things it cannot measure — skew,
# blur, noise, contrast, exact per-page text — are returned as
# "not measured in M1", never guessed. PDF page counts from raw bytes
# are ESTIMATES (compressed object streams hide /Type /Page markers);
# M2 replaces them with exact counts.
#
# Every rejection carries a machine-readable code so the API can
# report exactly why a file was refused. Nothing is silently skipped:
# a rejected file produces a ValidationReport with the reasons.

from __future__ import annotations

import hashlib
import io
import re
import struct
import zipfile
from dataclasses import dataclass, field

from app.config import Settings


@dataclass
class ValidationIssue:
    code: str
    message: str
    severity: str = "error"  # "error" (reject) or "warning" (accept, flag)


@dataclass
class ImageInfo:
    width_px: int | None = None
    height_px: int | None = None
    dpi: float | None = None
    rotation_degrees: int | None = None
    channels: int = 3


@dataclass
class ValidationReport:
    filename: str
    extension: str
    mime_type: str | None = None
    size_bytes: int = 0
    sha256: str = ""
    issues: list[ValidationIssue] = field(default_factory=list)
    # PDF findings (None when not a PDF).
    pdf_encrypted: bool = False
    pdf_page_count_estimate: int | None = None
    pdf_has_text_operators: bool | None = None
    pdf_has_images: bool | None = None
    # Image findings (None when not an image).
    image: ImageInfo | None = None
    decompression_ratio: float | None = None

    @property
    def valid(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]


# extension -> (mime, magic-byte prefixes). txt/docx have no single
# magic prefix and are checked structurally instead.
MAGIC: dict[str, tuple[bytes, ...]] = {
    "pdf": (b"%PDF-",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "webp": (b"RIFF",),  # + "WEBP" at offset 8, checked separately
    "tiff": (b"II*\x00", b"MM\x00*"),
    "tif": (b"II*\x00", b"MM\x00*"),
}

MIME: dict[str, str] = {
    "pdf": "application/pdf",
    "txt": "text/plain",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "tiff": "image/tiff",
    "tif": "image/tiff",
}

SUPPORTED_EXTENSIONS = frozenset(MIME)


def _sniff_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _check_magic(data: bytes, extension: str, report: ValidationReport) -> None:
    prefixes = MAGIC.get(extension)
    if prefixes is None:
        return  # txt / docx: structural checks below
    if not any(data.startswith(p) for p in prefixes):
        report.issues.append(
            ValidationIssue(
                "magic_bytes_mismatch",
                f"File extension is .{extension} but the first bytes do not match that format.",
            )
        )
        return
    if extension == "webp" and data[8:12] != b"WEBP":
        report.issues.append(
            ValidationIssue(
                "magic_bytes_mismatch",
                "RIFF container is not a WebP image (missing WEBP marker).",
            )
        )


def _check_docx(data: bytes, report: ValidationReport) -> None:
    if not data.startswith(b"PK\x03\x04"):
        report.issues.append(
            ValidationIssue("magic_bytes_mismatch", "File is not a ZIP/DOCX container.")
        )
        return
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            if "word/document.xml" not in names:
                report.issues.append(
                    ValidationIssue(
                        "not_a_docx",
                        "ZIP container has no word/document.xml; not a Word document.",
                    )
                )
    except zipfile.BadZipFile:
        report.issues.append(ValidationIssue("corrupt_file", "DOCX/ZIP container is corrupt."))


def _check_txt(data: bytes, report: ValidationReport) -> None:
    sample = data[:8192]
    if b"\x00" in sample:
        report.issues.append(
            ValidationIssue("not_plain_text", "File contains NUL bytes; not plain text.")
        )
        return
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        report.issues.append(
            ValidationIssue(
                "text_encoding",
                "Text is not valid UTF-8. Only UTF-8 plain text is accepted in M1.",
                severity="warning",
            )
        )


# --- image dimension parsers (stdlib only) -------------------------------


def _png_info(data: bytes) -> ImageInfo:
    info = ImageInfo(channels=3)
    if len(data) < 33 or data[12:16] != b"IHDR":
        return info
    width, height, bit_depth, color_type = struct.unpack(">IIBB", data[16:26])
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type, 3)
    info.width_px, info.height_px, info.channels = width, height, channels
    # pHYs chunk: pixels per metre -> DPI.
    pos = 8
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        ctype = data[pos + 4 : pos + 8]
        if ctype == b"pHYs" and length >= 9 and data[pos + 17] == 1:
            ppm = struct.unpack(">I", data[pos + 8 : pos + 12])[0]
            if ppm > 0:
                info.dpi = round(ppm / 39.3701, 2)
            break
        if ctype == b"IEND":
            break
        pos += 12 + length
    return info


def _jpeg_info(data: bytes) -> ImageInfo:
    info = ImageInfo(channels=3)
    pos = 2
    exif_orientation: int | None = None
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            break
        marker = data[pos + 1]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        length = struct.unpack(">H", data[pos + 2 : pos + 4])[0]
        segment = data[pos + 4 : pos + 2 + length]
        if marker in (0xC0, 0xC1, 0xC2):  # SOF0/1/2: precision, H, W
            if len(segment) >= 5:
                info.height_px = struct.unpack(">H", segment[1:3])[0]
                info.width_px = struct.unpack(">H", segment[3:5])[0]
        elif marker == 0xE0 and segment[:5] == b"JFIF\x00":  # density
            if len(segment) >= 12:
                unit = segment[7]
                x_density = struct.unpack(">H", segment[8:10])[0]
                if unit == 1 and x_density > 0:
                    info.dpi = float(x_density)
                elif unit == 2 and x_density > 0:
                    info.dpi = round(x_density * 2.54, 2)
        elif marker == 0xE1 and segment[:6] == b"Exif\x00\x00":
            exif_orientation = _exif_orientation(segment[6:])
        pos += 2 + length
        if info.width_px is not None and marker != 0xE1:
            break
    if exif_orientation in (5, 6, 7, 8):
        info.rotation_degrees = 90 if exif_orientation in (5, 6) else 270
    elif exif_orientation in (3, 4):
        info.rotation_degrees = 180
    elif exif_orientation in (1, 2):
        info.rotation_degrees = 0
    return info


def _exif_orientation(data: bytes) -> int | None:
    """Read EXIF Orientation (tag 0x0112) from a TIFF header in `data`."""
    if len(data) < 8:
        return None
    endian = "<" if data[:2] == b"II" else ">" if data[:2] == b"MM" else None
    if endian is None:
        return None
    try:
        ifd_offset = struct.unpack(endian + "I", data[4:8])[0]
        count = struct.unpack(endian + "H", data[ifd_offset : ifd_offset + 2])[0]
        for i in range(count):
            entry = data[ifd_offset + 2 + i * 12 : ifd_offset + 2 + (i + 1) * 12]
            if len(entry) < 12:
                break
            tag = struct.unpack(endian + "H", entry[0:2])[0]
            if tag == 0x0112:
                return int(struct.unpack(endian + "H", entry[8:10])[0])
    except (struct.error, IndexError):
        return None
    return None


def _webp_info(data: bytes) -> ImageInfo:
    info = ImageInfo(channels=4)
    if len(data) < 20:
        return info
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        w = int.from_bytes(data[24:27], "little") + 1
        h = int.from_bytes(data[27:30], "little") + 1
        info.width_px, info.height_px = w, h
    elif chunk == b"VP8L" and len(data) >= 21:
        b0, b1, b2, b3 = data[17:21]
        w = ((b1 & 0x3F) << 8 | b0) + 1
        h = ((b3 & 0x0F) << 10 | (b2 << 2) | ((b1 >> 6) & 0x03)) + 1
        info.width_px, info.height_px = w, h
    elif chunk == b"VP8 " and len(data) >= 26:
        w = struct.unpack("<H", data[24:26])[0] & 0x3FFF
        h = struct.unpack("<H", data[26:28])[0] & 0x3FFF
        info.width_px, info.height_px = w, h
    return info


def _tiff_info(data: bytes) -> ImageInfo:
    info = ImageInfo(channels=3)
    endian = "<" if data[:2] == b"II" else ">"
    try:
        ifd_offset = struct.unpack(endian + "I", data[4:8])[0]
        count = struct.unpack(endian + "H", data[ifd_offset : ifd_offset + 2])[0]
        tags: dict[int, int] = {}
        for i in range(count):
            entry = data[ifd_offset + 2 + i * 12 : ifd_offset + 2 + (i + 1) * 12]
            if len(entry) < 12:
                break
            tag, typ = struct.unpack(endian + "HH", entry[0:4])
            value = entry[8:12]
            if typ == 3:
                tags[tag] = struct.unpack(endian + "H", value[0:2])[0]
            elif typ == 4:
                tags[tag] = struct.unpack(endian + "I", value[0:4])[0]
        info.width_px = tags.get(256)
        info.height_px = tags.get(257)
        info.channels = tags.get(277, 3)
        if 274 in tags:
            orientation = tags[274]
            info.rotation_degrees = {1: 0, 3: 180, 6: 90, 8: 270}.get(orientation)
    except (struct.error, IndexError):
        pass
    return info


IMAGE_PARSERS = {
    "png": _png_info,
    "jpg": _jpeg_info,
    "jpeg": _jpeg_info,
    "webp": _webp_info,
    "tiff": _tiff_info,
    "tif": _tiff_info,
}


# --- PDF structure checks (byte-level, heuristic) -------------------------


def _check_pdf(data: bytes, report: ValidationReport) -> None:
    if not data.startswith(b"%PDF-"):
        report.issues.append(
            ValidationIssue("magic_bytes_mismatch", "File does not start with %PDF-.")
        )
        return
    # %%EOF must appear near the end of a well-formed PDF.
    tail = data[-1024:]
    if b"%%EOF" not in tail:
        report.issues.append(
            ValidationIssue(
                "pdf_truncated",
                "No %%EOF marker in the last 1 KB; the file looks truncated or corrupt.",
            )
        )
    if re.search(rb"/Encrypt\s", data[:65536]):
        report.pdf_encrypted = True
        report.issues.append(
            ValidationIssue(
                "pdf_encrypted",
                "PDF is encrypted (password-protected). Encrypted files are "
                "reported, never decrypted or bypassed.",
            )
        )
    # Page-count estimate: /Type /Page markers (not /Pages). Compressed
    # object streams hide these, so the count is a lower bound and may
    # be None (unknown) — M2 (PyMuPDF) makes it exact.
    page_markers = len(re.findall(rb"/Type\s*/Page[^s]", data))
    count_values = [int(m) for m in re.findall(rb"/Count\s+(\d+)", data[:65536])]
    estimate = max([page_markers] + count_values) if (page_markers or count_values) else None
    report.pdf_page_count_estimate = estimate
    report.pdf_has_text_operators = bool(re.search(rb"\bTj\b|\bTJ\b", data))
    report.pdf_has_images = b"/Image" in data or b"/XObject" in data
    if estimate is not None and estimate == 0:
        report.issues.append(ValidationIssue("pdf_no_pages", "No pages found in the PDF."))


def validate_file(filename: str, data: bytes, settings: Settings) -> ValidationReport:
    """Validate one uploaded file's bytes. Pure function of (bytes, limits)."""
    report = ValidationReport(
        filename=filename,
        extension=_sniff_extension(filename),
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    if not data:
        report.issues.append(ValidationIssue("empty_file", "File is empty."))
        return report
    if report.size_bytes > settings.max_file_size_bytes:
        report.issues.append(
            ValidationIssue(
                "file_too_large",
                f"File is {report.size_bytes} bytes; limit is {settings.max_file_size_bytes}.",
            )
        )
        return report
    if report.extension not in SUPPORTED_EXTENSIONS:
        report.issues.append(
            ValidationIssue(
                "unsupported_type",
                f"Extension .{report.extension or '(none)'} is not supported. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}.",
            )
        )
        return report

    report.mime_type = MIME[report.extension]
    _check_magic(data, report.extension, report)
    if report.extension == "docx":
        _check_docx(data, report)
    elif report.extension == "txt":
        _check_txt(data, report)
    elif report.extension == "pdf":
        _check_pdf(data, report)
        if (
            report.pdf_page_count_estimate is not None
            and report.pdf_page_count_estimate > settings.max_pages_per_job
        ):
            report.issues.append(
                ValidationIssue(
                    "too_many_pages",
                    f"Estimated {report.pdf_page_count_estimate} pages; limit is "
                    f"{settings.max_pages_per_job}. Rejected — split the document "
                    "and re-upload.",
                )
            )
    elif report.extension in IMAGE_PARSERS:
        info = IMAGE_PARSERS[report.extension](data)
        report.image = info
        if info.width_px is None or info.height_px is None:
            report.issues.append(
                ValidationIssue(
                    "image_unreadable",
                    "Could not read image dimensions; the image looks corrupt.",
                )
            )
        else:
            if (
                info.width_px > settings.max_image_dimension_px
                or info.height_px > settings.max_image_dimension_px
            ):
                report.issues.append(
                    ValidationIssue(
                        "image_too_large",
                        f"Image is {info.width_px}x{info.height_px}px; dimension "
                        f"limit is {settings.max_image_dimension_px}px.",
                    )
                )
            pixels = info.width_px * info.height_px
            if pixels > settings.max_image_pixels:
                report.issues.append(
                    ValidationIssue(
                        "image_too_many_pixels",
                        f"Image has {pixels} pixels; limit is {settings.max_image_pixels}.",
                    )
                )
            decoded = pixels * info.channels
            ratio = decoded / max(report.size_bytes, 1)
            report.decompression_ratio = round(ratio, 2)
            if ratio > settings.max_decompression_ratio:
                # WARNING only, never a rejection: blank pages and
                # solid-colour images legitimately compress 100x+.
                # The hard bomb bound is the absolute pixel cap above
                # (decoded size <= max_image_pixels * channels).
                report.issues.append(
                    ValidationIssue(
                        "decompression_ratio_high",
                        f"Decoded size (~{decoded} bytes) is {ratio:.0f}x the "
                        "file size; flagged for review, not rejected.",
                        severity="warning",
                    )
                )
    return report
