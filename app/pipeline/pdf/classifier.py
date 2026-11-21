# OfficerPath AI — PDF Engine (Phase 1, M2)
# Real per-page classification from PyMuPDF evidence (prompt §6).
# Replaces the M1 byte heuristic for PDFs (classifier.py in
# ingestion/ still owns image/txt/docx files and the fallback when
# no PDF bytes are available). Decided PER PAGE, never per document.
#
# Rules (thresholds are the module constants in analysis.py):
# - blank: no text, no raster images, no vector drawings.
# - unreadable: the page could not be read at all (extraction error).
# - digital: a real text layer and little image coverage.
# - scanned: no text layer, raster image(s) covering most of the page.
# - mixed: text layer AND substantial image coverage, or a small text
#   layer (page numbers / headers only) on an image page.
# - unknown: anything else (e.g. a vector-only figure page — no text,
#   no raster image). Unknown is recorded with the reason, never guessed.

from __future__ import annotations

from app.pipeline.ingestion.classifier import PageClassification
from app.pipeline.pdf.analysis import (
    MIN_TEXT_CHARS_FOR_DIGITAL,
    MIXED_IMAGE_COVERAGE,
    SCANNED_IMAGE_COVERAGE,
    PageAnalysis,
)


def classify_page(page: PageAnalysis) -> PageClassification:
    """Classify one analysed page from its measured evidence."""
    method = "pymupdf-evidence"
    if page.error is not None:
        return PageClassification(
            page_number=page.page_number,
            classification="unreadable",
            method=method,
            confidence=0.9,
            note=f"Page could not be read: {page.error}",
        )
    has_text = page.text_char_count >= MIN_TEXT_CHARS_FOR_DIGITAL
    has_images = page.image_count > 0
    if not has_text and not has_images and page.drawing_count == 0:
        return PageClassification(
            page_number=page.page_number,
            classification="blank",
            method=method,
            confidence=0.9,
            note="No text, no raster images, no vector drawings on the page.",
        )
    if has_text and page.image_coverage <= MIXED_IMAGE_COVERAGE:
        return PageClassification(
            page_number=page.page_number,
            classification="digital",
            method=method,
            confidence=0.95,
            note=(
                f"Text layer with {page.text_char_count} characters, "
                f"image coverage {page.image_coverage:.2f}."
            ),
        )
    if not has_text and has_images and page.image_coverage >= SCANNED_IMAGE_COVERAGE:
        return PageClassification(
            page_number=page.page_number,
            classification="scanned",
            method=method,
            confidence=0.9,
            note=(
                f"No text layer; {page.image_count} raster image(s) covering "
                f"{page.image_coverage:.2f} of the page."
            ),
        )
    if has_text and has_images:
        return PageClassification(
            page_number=page.page_number,
            classification="mixed",
            method=method,
            confidence=0.8,
            note=(
                f"Text layer ({page.text_char_count} chars) plus raster images "
                f"covering {page.image_coverage:.2f} of the page."
            ),
        )
    if not has_text and has_images:
        # Small image(s) only: a figure, a stamp, a logo — not a page
        # picture. Do not call it scanned; the evidence does not say that.
        return PageClassification(
            page_number=page.page_number,
            classification="unknown",
            method=method,
            confidence=None,
            note=(
                f"No text layer and only {page.image_count} small raster "
                f"image(s) (coverage {page.image_coverage:.2f}); not enough "
                "evidence to call this a scanned page."
            ),
        )
    # Text below the digital threshold, no images: a page number or a
    # stray glyph — or a vector-only figure page.
    return PageClassification(
        page_number=page.page_number,
        classification="unknown",
        method=method,
        confidence=None,
        note=(
            f"Only {page.text_char_count} text characters, no raster images, "
            f"{page.drawing_count} vector drawing(s); not enough evidence "
            "for a classification."
        ),
    )


def classify_pages_from_analysis(pages: list[PageAnalysis]) -> list[PageClassification]:
    return [classify_page(p) for p in pages]
