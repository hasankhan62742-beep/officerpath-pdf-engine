# OfficerPath AI — PDF Engine (Phase 1, M3)
# Digital text extractor (prompt §8): the FIRST engine in the
# routing order. Wherever a page has a reliable text layer, its text
# is exact — no OCR is run, no confidence is invented, and every
# block carries its font/style metadata (font name, size, bold,
# italic, colour) so M5 can detect bold/highlight style markings
# from the text layer itself.
#
# Input: PDF bytes + page number (from PageContext.pdf_bytes). The
# M2 classifier decides whether a page HAS a reliable text layer;
# this engine only extracts — it never decides. A page with fewer
# than MIN_TEXT_CHARS_FOR_DIGITAL characters is reported as
# "no reliable text layer" (empty result + reason), never padded.
#
# Blocks are PyMuPDF dict-blocks (one text block = one OCRBlock),
# ordered by the shared column geometry (layout/columns.py) so the
# digital route and the OCR routes agree on reading order.

from __future__ import annotations

import fitz  # PyMuPDF

from app.pipeline.interfaces import BoundingBox, OCRBlock, PageContext
from app.pipeline.layout.columns import reading_order_indices
from app.pipeline.ocr.normalize import detect_script

ENGINE_NAME = "digital-pymupdf"
ENGINE_VERSION = "1.26.3"  # PyMuPDF version pinned in requirements.txt
MIN_TEXT_CHARS_FOR_DIGITAL = 20


class DigitalExtractor:
    """OCREngine for digital PDF pages. name/version satisfy the
    OCREngine protocol; recognize() returns blocks in reading order.
    """

    name = ENGINE_NAME

    @property
    def version(self) -> str:
        return ENGINE_VERSION

    def recognize(self, page: PageContext) -> list[OCRBlock]:
        if page.pdf_bytes is None:
            raise ValueError("DigitalExtractor needs pdf_bytes on the PageContext.")
        try:
            doc = fitz.open(stream=page.pdf_bytes, filetype="pdf")
        except Exception as exc:
            raise ValueError(f"PyMuPDF could not open the PDF: {exc}") from exc
        try:
            if doc.is_encrypted:
                raise ValueError("PDF is encrypted; decryption is never attempted.")
            if page.page_number < 1 or page.page_number > len(doc):
                raise ValueError(f"Page {page.page_number} out of range (1..{len(doc)}).")
            fitz_page = doc[page.page_number - 1]
            return _extract_page(fitz_page, page)
        finally:
            doc.close()


def _extract_page(fitz_page: fitz.Page, page: PageContext) -> list[OCRBlock]:
    text_dict = fitz_page.get_text("dict")
    width = float(fitz_page.rect.width)
    height = float(fitz_page.rect.height)
    raw_blocks: list[dict] = []
    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:  # 0 = text block; 1 = image block
            continue
        lines: list[str] = []
        fonts: set[str] = set()
        sizes: list[float] = []
        bold = False
        bold_lines: list[int] = []
        italic = False
        colours: set[str] = set()
        for line in block.get("lines", []):
            line_text = "".join(span.get("text", "") for span in line.get("spans", []))
            if line_text:
                lines.append(line_text)
            line_bold = False
            for span in line.get("spans", []):
                if span.get("font"):
                    fonts.add(str(span["font"]))
                if span.get("size"):
                    sizes.append(float(span["size"]))
                flags = int(span.get("flags", 0))
                if flags & 16:  # PyMuPDF span flag: bold
                    bold = True
                    line_bold = True
                if flags & 2:  # PyMuPDF span flag: italic
                    italic = True
                if span.get("color") is not None:
                    colours.add(f"#{int(span['color']):06x}")
            if line_bold and line_text:
                # M4 (D17): per-line bold indices, 0-based within the
                # block. The extract service appends U+E000 to each
                # bold line so the parser can read the bold signal
                # per option (block-level "bold" is too coarse).
                bold_lines.append(len(lines) - 1)
        text = "\n".join(lines).strip()
        if not text:
            continue
        bbox = block.get("bbox", [0, 0, 0, 0])
        raw_blocks.append(
            {
                "text": text,
                "bbox": BoundingBox(
                    x_min=max(0.0, bbox[0] / width),
                    y_min=max(0.0, bbox[1] / height),
                    x_max=min(1.0, bbox[2] / width),
                    y_max=min(1.0, bbox[3] / height),
                ),
                "style": {
                    "fonts": sorted(fonts),
                    "size_pt": round(max(sizes), 1) if sizes else None,
                    "bold": bold,
                    "bold_lines": bold_lines,  # M4 (D17): 0-based line indices
                    "italic": italic,
                    "colours": sorted(colours),
                },
            }
        )
    if sum(len(b["text"]) for b in raw_blocks) < MIN_TEXT_CHARS_FOR_DIGITAL:
        return []
    ranks = reading_order_indices([b["bbox"] for b in raw_blocks])
    ordered = sorted(enumerate(raw_blocks), key=lambda pair: ranks[pair[0]])
    blocks: list[OCRBlock] = []
    for rank, (_index, raw) in enumerate(ordered):
        blocks.append(
            OCRBlock(
                text=raw["text"],
                bbox=raw["bbox"],
                page_number=page.page_number,
                reading_order=rank,  # dense 0..n-1 in reading order
                confidence=None,  # digital text has no OCR confidence; None, never 1.0
                word_confidences=None,
                language=detect_script(raw["text"]),
                engine=ENGINE_NAME,
                engine_version=ENGINE_VERSION,
                style=raw["style"],
            )
        )
    return blocks
