# OfficerPath AI — PDF Engine (Phase 1, M1)
# Per-page classification (prompt §6): digital / scanned / mixed /
# blank / unreadable / unknown — decided PER PAGE, never per document.
#
# M1 method is a BYTE-LEVEL HEURISTIC (no PyMuPDF, no OpenCV yet):
# - single image file -> one page, "scanned" (an image has no text layer).
# - txt/docx -> one logical page, "digital".
# - PDF -> text operators (Tj/TJ) and image XObjects are searched in
#   the raw bytes. Compressed object streams hide both, so when neither
#   is found the pages are "unknown" with the reason recorded — M2
#   (PyMuPDF rendering + text-layer check per page) makes this exact.
# Blank / unreadable pages CANNOT be detected from raw bytes; M1 never
# claims them. A page is only ever labelled what the evidence supports.

from __future__ import annotations

from dataclasses import dataclass

from app.pipeline.ingestion.validator import ValidationReport


@dataclass
class PageClassification:
    page_number: int
    classification: str  # digital | scanned | mixed | blank | unreadable | unknown
    method: str
    confidence: float | None
    width_px: int | None = None
    height_px: int | None = None
    dpi_estimate: float | None = None
    rotation_degrees: int | None = None
    note: str | None = None


def classify_pages(report: ValidationReport) -> list[PageClassification]:
    """Classify every page of a validated file from the byte-level evidence."""
    ext = report.extension
    if ext in ("jpg", "jpeg", "png", "webp", "tiff", "tif"):
        img = report.image
        return [
            PageClassification(
                page_number=1,
                classification="scanned",
                method="file-type",
                confidence=0.9,
                width_px=img.width_px if img else None,
                height_px=img.height_px if img else None,
                dpi_estimate=img.dpi if img else None,
                rotation_degrees=img.rotation_degrees if img else None,
                note="Single image file: one page, no text layer.",
            )
        ]
    if ext in ("txt", "docx"):
        return [
            PageClassification(
                page_number=1,
                classification="digital",
                method="file-type",
                confidence=0.9,
                note="Text document: one logical page with a text layer.",
            )
        ]
    if ext == "pdf":
        count = report.pdf_page_count_estimate or 1
        has_text = report.pdf_has_text_operators
        has_images = report.pdf_has_images
        if has_text and has_images:
            label, confidence = "mixed", 0.6
            note = "Byte heuristic: text operators and image XObjects both present."
        elif has_text:
            label, confidence = "digital", 0.6
            note = "Byte heuristic: text operators found, no image XObjects."
        elif has_images:
            label, confidence = "scanned", 0.6
            note = "Byte heuristic: image XObjects found, no text operators."
        else:
            label, confidence = "unknown", None
            note = (
                "Byte heuristic found neither text operators nor image markers "
                "(object streams are usually compressed). Exact classification "
                "needs M2 PDF rendering — recorded as unknown, not guessed."
            )
        return [
            PageClassification(
                page_number=n,
                classification=label,
                method="byte-heuristic",
                confidence=confidence,
                note=note,
            )
            for n in range(1, count + 1)
        ]
    return []
