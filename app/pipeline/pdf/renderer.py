# OfficerPath AI — PDF Engine (Phase 1, M2)
# Rendering at bounded DPI (prompt §6/§7). One page at a time, never
# the whole document in memory: a caller renders a page, processes
# it, releases the buffers, then moves on. The DPI guard is the
# memory guard — a page that would exceed max_render_pixels at the
# requested DPI is rendered at a lower DPI instead, and the DPI
# actually used is always returned (never silently claimed).
#
# Renders are colour PNGs: the colour copy is what highlight
# detection (M5) needs, and binarisation erases highlights, so the
# original render is always kept alongside any processed version.

from __future__ import annotations

import io

import fitz  # PyMuPDF
from PIL import Image


class RenderResult:
    """One rendered page: colour PNG bytes + the facts about the render."""

    def __init__(
        self,
        *,
        page_number: int,
        png_bytes: bytes,
        width_px: int,
        height_px: int,
        dpi_requested: int,
        dpi_used: float,
        source: str,
    ) -> None:
        self.page_number = page_number
        self.png_bytes = png_bytes
        self.width_px = width_px
        self.height_px = height_px
        self.dpi_requested = dpi_requested
        self.dpi_used = dpi_used
        self.source = source

    def pixel_count(self) -> int:
        return self.width_px * self.height_px


def _bounded_dpi(width_pt: float, height_pt: float, dpi: int, max_pixels: int) -> float:
    """Lower the DPI until the render fits max_pixels (never below 72)."""
    while dpi > 72:
        px = (width_pt / 72.0 * dpi) * (height_pt / 72.0 * dpi)
        if px <= max_pixels:
            return float(dpi)
        dpi = max(72, int(dpi * 0.8))
    return 72.0


def render_pdf_page(
    data: bytes,
    page_number: int,
    dpi: int = 200,
    max_pixels: int = 12_000_000,
) -> RenderResult:
    """Render one PDF page (1-based) to a colour PNG.

    Raises ValueError on a bad PDF / bad page number. The page
    rotation stored in the PDF is applied by the render (a rotated
    page comes out upright); content-level rotation (a sideways scan
    inside an upright page) is NOT detected here — that needs OCR
    geometry (M3) and is recorded as a limitation, not guessed.
    """
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"PyMuPDF could not open the PDF: {exc}") from exc
    try:
        if doc.is_encrypted:
            raise ValueError("PDF is encrypted; decryption is never attempted.")
        if page_number < 1 or page_number > len(doc):
            raise ValueError(f"Page {page_number} out of range (1..{len(doc)}).")
        page = doc[page_number - 1]
        dpi_used = _bounded_dpi(page.rect.width, page.rect.height, dpi, max_pixels)
        zoom = dpi_used / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        width_px, height_px = pix.width, pix.height
        png_bytes = pix.tobytes("png")
        return RenderResult(
            page_number=page_number,
            png_bytes=png_bytes,
            width_px=width_px,
            height_px=height_px,
            dpi_requested=dpi,
            dpi_used=dpi_used,
            source="pymupdf",
        )
    finally:
        doc.close()


def render_image_file(
    data: bytes,
    page_number: int = 1,
    dpi: int = 200,
    max_pixels: int = 12_000_000,
) -> RenderResult:
    """Normalise one image file to a colour PNG, bounded by the same
    pixel cap (downscaled with Lanczos when it would exceed it).
    The returned PNG is the page render for an image-only document.
    Raises ValueError when Pillow cannot open the image."""
    try:
        opened = Image.open(io.BytesIO(data))
        opened.load()
    except Exception as exc:
        raise ValueError(f"Pillow could not open the image: {exc}") from exc
    image: Image.Image = opened.convert("RGB")
    width_px, height_px = image.size
    if width_px * height_px > max_pixels:
        scale = (max_pixels / (width_px * height_px)) ** 0.5
        image = image.resize(
            (max(1, int(width_px * scale)), max(1, int(height_px * scale))),
            Image.Resampling.LANCZOS,
        )
        width_px, height_px = image.size
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return RenderResult(
        page_number=page_number,
        png_bytes=buffer.getvalue(),
        width_px=width_px,
        height_px=height_px,
        dpi_requested=dpi,
        dpi_used=float(dpi),
        source="pillow",
    )
