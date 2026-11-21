# OfficerPath AI — PDF Engine (Phase 1, M2)
# PDF analysis with PyMuPDF (prompt §6): per-page digital-text
# detection, page sizes, rotation, embedded images, font/style
# metadata. No OCR here — this module measures what is IN the file
# so M3 knows which pages need OCR and which have exact text.
#
# Evidence rule: every number comes from the file itself. A page is
# only labelled what the evidence supports; genuinely undecidable
# pages are "unknown" with the reason recorded (see classifier).

from __future__ import annotations

from dataclasses import dataclass, field

import fitz  # PyMuPDF

# A page needs at least this many text characters before its text
# layer counts as real content (below it, a stray header/footer
# glyph or a page number must not make a scanned page "digital").
MIN_TEXT_CHARS_FOR_DIGITAL = 20
# Image coverage (fraction of page area covered by raster images)
# above this makes a text-bearing page "mixed" rather than "digital".
MIXED_IMAGE_COVERAGE = 0.15
# Image coverage above this with no text layer means the page is a
# picture of a page, not a document with a text layer.
SCANNED_IMAGE_COVERAGE = 0.5


@dataclass
class PageAnalysis:
    """Measured facts about ONE PDF page. No interpretation beyond
    the raw counts — classification lives in classifier.py."""

    page_number: int
    width_pt: float
    height_pt: float
    rotation_degrees: int
    text_char_count: int
    text_span_count: int
    image_count: int
    image_coverage: float  # 0.0-1.0 of page area covered by raster images
    drawing_count: int
    fonts: list[str] = field(default_factory=list)
    embedded_image_dpis: list[float] = field(default_factory=list)
    has_text_layer: bool = False
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "page_number": self.page_number,
            "width_pt": round(self.width_pt, 2),
            "height_pt": round(self.height_pt, 2),
            "rotation_degrees": self.rotation_degrees,
            "text_char_count": self.text_char_count,
            "text_span_count": self.text_span_count,
            "image_count": self.image_count,
            "image_coverage": round(self.image_coverage, 4),
            "drawing_count": self.drawing_count,
            "fonts": self.fonts,
            "embedded_image_dpis": [round(d, 1) for d in self.embedded_image_dpis],
            "has_text_layer": self.has_text_layer,
            "error": self.error,
        }


@dataclass
class DocumentAnalysis:
    """Measured facts about one PDF document."""

    page_count: int
    pdf_version: str | None = None
    encrypted: bool = False
    metadata: dict | None = None
    pages: list[PageAnalysis] = field(default_factory=list)
    error: str | None = None


def analyze_pdf(data: bytes) -> DocumentAnalysis:
    """Analyse a PDF from bytes. Raises ValueError on a file PyMuPDF
    cannot open (corrupt / not a PDF); encrypted files raise
    ValueError too — decryption is never attempted (prompt §6)."""
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"PyMuPDF could not open the PDF: {exc}") from exc
    try:
        if doc.is_encrypted:
            raise ValueError("PDF is encrypted; decryption is never attempted.")
        pages: list[PageAnalysis] = []
        for index, page in enumerate(doc):
            pages.append(_analyze_page(page, index + 1))
        return DocumentAnalysis(
            page_count=len(pages),
            pdf_version=doc.pdf_version() if hasattr(doc, "pdf_version") else None,
            encrypted=False,
            metadata={k: str(v) for k, v in (doc.metadata or {}).items()},
            pages=pages,
        )
    finally:
        doc.close()


def _analyze_page(page: fitz.Page, page_number: int) -> PageAnalysis:
    rect = page.rect
    page_area = max(rect.width * rect.height, 1.0)
    rotation = int(page.rotation)
    try:
        text = page.get_text("text")
        text_dict = page.get_text("dict")
    except Exception as exc:  # a damaged page must not kill the document
        return PageAnalysis(
            page_number=page_number,
            width_pt=rect.width,
            height_pt=rect.height,
            rotation_degrees=rotation,
            text_char_count=0,
            text_span_count=0,
            image_count=0,
            image_coverage=0.0,
            drawing_count=0,
            error=f"text extraction failed: {exc}",
        )
    text_chars = len(text.strip())
    spans = 0
    fonts: set[str] = set()
    for block in text_dict.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                spans += 1
                if span.get("font"):
                    fonts.add(str(span["font"]))
    image_infos = page.get_image_info(xrefs=True)
    image_area = 0.0
    dpis: list[float] = []
    for info in image_infos:
        bbox = info.get("bbox")
        if bbox:
            image_area += (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        width = info.get("width") or 0
        height = info.get("height") or 0
        if bbox and width and height:
            phys_w_in = max((bbox[2] - bbox[0]) / 72.0, 0.01)
            dpis.append(width / phys_w_in)
    try:
        drawings = len(page.get_drawings())
    except Exception:
        drawings = 0
    return PageAnalysis(
        page_number=page_number,
        width_pt=rect.width,
        height_pt=rect.height,
        rotation_degrees=rotation,
        text_char_count=text_chars,
        text_span_count=spans,
        image_count=len(image_infos),
        image_coverage=min(image_area / page_area, 1.0),
        drawing_count=drawings,
        fonts=sorted(fonts),
        embedded_image_dpis=dpis,
        has_text_layer=text_chars >= MIN_TEXT_CHARS_FOR_DIGITAL,
    )
