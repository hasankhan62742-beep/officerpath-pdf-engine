# OfficerPath AI — PDF Engine (Phase 1, M3)
# Layout pipeline stage: OCR_DONE -> LAYOUT_DONE, one page at a time.
#
# Same wiring discipline as the OCR stage (prompt §5.3): a PIPELINE
# STAGE, called by the M7 worker (or the CLI script / tests until
# then). It runs the GeometryLayoutAnalyzer over one page's OCR
# blocks, persists the layout JSON on the document_pages row
# (layout_applied, Alembic 0002), and records the stage transition.
# A page failure is a ProcessingError row; the document continues.
#
# Cross-page continuation: a page whose LAST region is a question or
# option, followed by a page whose FIRST region is an option or plain
# text, is flagged as a continuation CANDIDATE (method
# "layout-adjacency", confidence 0.5) linking both pages. It is a
# flag for M4 to verify, not a decision — M4 owns question
# boundaries. The candidate is stored on the SECOND page's layout
# (continues_from_page) and on the first page's (continues_to_page).
#
# Header/footer repetition: the same short header/footer text on
# >= 3 pages is promoted from "positional candidate" to
# "repeated header/footer" in the service (stronger evidence than a
# single page's position). The per-page analyser only flags the
# positional candidates.

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field

from app.config import Settings
from app.pipeline.ingestion.service import StageRecorder
from app.pipeline.interfaces import BoundingBox, OCRBlock, PageContext, PipelineStage
from app.pipeline.layout.analyzer import GeometryLayoutAnalyzer
from app.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class LayoutPageInput:
    """One page's inputs to the layout stage."""

    page_number: int
    blocks: list[OCRBlock] = field(default_factory=list)
    images: list[BoundingBox] = field(default_factory=list)
    rotation_hint: dict | None = None


@dataclass
class PageLayoutResult:
    page_number: int
    layout: dict | None = None
    error: str | None = None


@dataclass
class DocumentLayoutResult:
    document_id: uuid.UUID
    pages: list[PageLayoutResult] = field(default_factory=list)

    @property
    def pages_processed(self) -> int:
        return len([p for p in self.pages if p.error is None])


def run_layout_stage(
    *,
    settings: Settings,
    recorder: StageRecorder,
    document_id: uuid.UUID,
    job_id: uuid.UUID | None,
    pages: list[LayoutPageInput],
    correlation_id: str | None = None,
    analyzer: GeometryLayoutAnalyzer | None = None,
) -> DocumentLayoutResult:
    """Run layout analysis over one document's pages (in page order).
    Never raises for a page-level failure."""
    analyzer = analyzer or GeometryLayoutAnalyzer()
    result = DocumentLayoutResult(document_id=document_id)
    layouts: dict[int, dict] = {}
    for page_input in pages:
        try:
            context = PageContext(
                document_id=document_id,
                page_number=page_input.page_number,
                storage_path="",
                correlation_id=correlation_id or "",
            )
            layout = analyzer.analyze(
                context,
                page_input.blocks,
                images=page_input.images,
                rotation_hint=page_input.rotation_hint,
            )
            layouts[page_input.page_number] = layout
            result.pages.append(PageLayoutResult(page_number=page_input.page_number, layout=layout))
        except Exception as exc:  # a page failure never fails the document
            result.pages.append(
                PageLayoutResult(page_number=page_input.page_number, error=f"layout_failed: {exc}")
            )
            recorder.record_error(
                document_id=document_id,
                job_id=job_id,
                page_number=page_input.page_number,
                stage=PipelineStage.LAYOUT_DONE.value,
                error_code="layout_failed",
                message=str(exc),
            )
    _apply_continuations(layouts)
    _apply_repeated_headers(layouts)
    for page_result in result.pages:
        if page_result.layout is None:
            continue
        recorder.update_page(
            document_id,
            page_result.page_number,
            layout_applied=page_result.layout,
        )
        recorder.record(
            document_id=document_id,
            job_id=job_id,
            stage=PipelineStage.LAYOUT_DONE,
            status="done",
            detail={
                "page_number": page_result.page_number,
                "column_count": page_result.layout.get("column_count"),
                "block_count": page_result.layout.get("block_count"),
                "tables": len(page_result.layout.get("tables", [])),
            },
            correlation_id=correlation_id,
        )
    return result


def _apply_continuations(layouts: dict[int, dict]) -> None:
    """Flag adjacent-page continuation candidates (see module
    docstring). Mutates the layout dicts in place."""
    for page_number in sorted(layouts):
        layout = layouts[page_number]
        next_layout = layouts.get(page_number + 1)
        if next_layout is None:
            continue
        regions = layout.get("regions", [])
        next_regions = next_layout.get("regions", [])
        if not regions or not next_regions:
            continue
        last = regions[-1].get("region")
        first = next_regions[0].get("region")
        if last in ("question", "option") and first in ("option", "text", "question"):
            layout["continues_to_page"] = page_number + 1
            layout["continuation_method"] = "layout-adjacency"
            layout["continuation_confidence"] = 0.5
            next_layout["continues_from_page"] = page_number
            next_layout["continuation_method"] = "layout-adjacency"
            next_layout["continuation_confidence"] = 0.5


def _apply_repeated_headers(layouts: dict[int, dict]) -> None:
    """Promote positional header/footer candidates that repeat
    verbatim on >= 3 pages. Mutates the layout dicts in place."""
    texts: Counter = Counter()
    for layout in layouts.values():
        for region in layout.get("regions", []):
            if region.get("header_footer"):
                texts[region.get("text_preview", "")] += 1
    repeated = {text for text, count in texts.items() if count >= 3 and text}
    if not repeated:
        return
    for layout in layouts.values():
        for region in layout.get("regions", []):
            if region.get("text_preview") in repeated:
                region["header_footer_repeated"] = True
