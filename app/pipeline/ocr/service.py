# OfficerPath AI — PDF Engine (Phase 1, M3)
# OCR pipeline stage: PREPROCESSING -> OCR_DONE, one page at a time.
#
# Wiring (prompt §5.3, same discipline as the M2 stage): this is a
# PIPELINE STAGE, not a request handler. The M7 worker calls
# run_ocr_stage for a stored document; until M7 exists, run it from
# the CLI script (scripts/run_m3_pipeline.py) or from tests. The
# stage reads the M2 renders from storage (processed render first,
# original render when no processed render exists), routes engines
# per page, persists every engine's blocks (the engine name on each
# row distinguishes them — disagreement outputs are both kept), and
# records the stage transition per page. A page failure is a
# ProcessingError row + a failed per-page stage record; the document
# continues with the next page.
#
# Engine failures are NOT document failures: an engine that cannot
# run (missing binary, failed model download) is recorded as
# "engine unavailable: <reason>" on that page and the router falls
# back to the next available engine. A page with NO available engine
# at all is recorded as failed with error code "no_ocr_engine".

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.config import Settings
from app.pipeline.ingestion.service import StageRecorder
from app.pipeline.interfaces import OCRBlock, PageContext, PipelineStage
from app.pipeline.ocr.registry import OCRRegistry, default_registry
from app.pipeline.ocr.router import compare_engines, deduplicate_blocks, route_page
from app.pipeline.ocr.tesseract import EngineUnavailableError
from app.storage.base import StorageBackend
from app.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class OcrPageInput:
    """One page's inputs to the OCR stage (built by the caller from
    the M2 result + storage)."""

    page_number: int
    classification: str
    render_path: str | None = None  # original colour render (storage)
    processed_render_path: str | None = None  # M2 processed render
    pdf_bytes: bytes | None = None  # the source PDF (digital route)


@dataclass
class PageOcrResult:
    page_number: int
    engines_run: list[str] = field(default_factory=list)
    engines_unavailable: dict[str, str] = field(default_factory=dict)
    block_count: int = 0
    blocks_by_engine: dict[str, int] = field(default_factory=dict)
    deduplicated: int = 0
    disagreement: dict | None = None
    error: str | None = None


@dataclass
class DocumentOcrResult:
    document_id: uuid.UUID
    pages: list[PageOcrResult] = field(default_factory=list)

    @property
    def pages_processed(self) -> int:
        return len([p for p in self.pages if p.error is None])


def build_registry(settings: Settings) -> OCRRegistry:
    """The production registry for these settings."""
    return default_registry(
        tesseract_languages=settings.tesseract_languages,
        tesseract_psm=settings.tesseract_psm,
        paddleocr_language=settings.paddleocr_language,
        paddleocr_enabled=settings.paddleocr_enabled,
    )


def run_ocr_stage(
    *,
    settings: Settings,
    storage: StorageBackend,
    recorder: StageRecorder,
    document_id: uuid.UUID,
    job_id: uuid.UUID | None,
    pages: list[OcrPageInput],
    correlation_id: str | None = None,
    registry: OCRRegistry | None = None,
) -> DocumentOcrResult:
    """Run OCR over one document's pages. Returns per-page results;
    never raises for a page-level failure (see module docstring)."""
    registry = registry or build_registry(settings)
    available = registry.available_names()
    unavailable = registry.unavailable_report()
    if unavailable:
        log.info(
            "ocr engines unavailable",
            extra={"fields": {"document_id": str(document_id), "engines": unavailable}},
        )
    result = DocumentOcrResult(document_id=document_id)
    for page_input in pages:
        page_result = _process_one_page(
            settings=settings,
            storage=storage,
            recorder=recorder,
            document_id=document_id,
            job_id=job_id,
            page_input=page_input,
            registry=registry,
            available=available,
            unavailable=unavailable,
            correlation_id=correlation_id,
        )
        result.pages.append(page_result)
    return result


def _load_render(storage: StorageBackend, page_input: OcrPageInput) -> bytes | None:
    """Processed render first (it is what OCR should read), original
    render as fallback. Returns None when neither exists in storage."""
    for path in (page_input.processed_render_path, page_input.render_path):
        if path is None:
            continue
        try:
            return storage.get(path)
        except Exception:
            continue
    return None


def _process_one_page(
    *,
    settings: Settings,
    storage: StorageBackend,
    recorder: StageRecorder,
    document_id: uuid.UUID,
    job_id: uuid.UUID | None,
    page_input: OcrPageInput,
    registry: OCRRegistry,
    available: list[str],
    unavailable: dict[str, str],
    correlation_id: str | None,
) -> PageOcrResult:
    page_result = PageOcrResult(
        page_number=page_input.page_number,
        engines_unavailable={name: reason for name, reason in unavailable.items()},
    )
    try:
        engine_names = route_page(page_input.classification, available)
        if not engine_names:
            page_result.error = (
                "no_ocr_engine: no engine available for "
                f"classification {page_input.classification!r}"
            )
            _record_page_failure(
                recorder,
                document_id,
                job_id,
                page_input,
                "no_ocr_engine",
                page_result.error,
                correlation_id,
            )
            return page_result
        image_png = _load_render(storage, page_input)
        context = PageContext(
            document_id=document_id,
            page_number=page_input.page_number,
            storage_path=page_input.render_path or "",
            classification=page_input.classification,
            image_png=image_png,
            pdf_bytes=page_input.pdf_bytes,
            correlation_id=correlation_id or "",
        )
        blocks_by_engine: dict[str, list[OCRBlock]] = {}
        for name in engine_names:
            engine = registry.engine(name)
            try:
                blocks = engine.recognize(context)
            except EngineUnavailableError as exc:
                page_result.engines_unavailable[name] = str(exc)
                log.info(
                    "ocr engine unavailable at runtime",
                    extra={"fields": {"engine": name, "reason": str(exc)}},
                )
                continue
            for block in blocks:
                block.engine_version = block.engine_version or getattr(engine, "version", None)
            blocks_by_engine[name] = blocks
            page_result.engines_run.append(name)
        if not blocks_by_engine:
            page_result.error = "no_ocr_engine: every routed engine was unavailable"
            _record_page_failure(
                recorder,
                document_id,
                job_id,
                page_input,
                "no_ocr_engine",
                page_result.error,
                correlation_id,
            )
            return page_result
        all_blocks: list[OCRBlock] = []
        if "digital-pymupdf" in blocks_by_engine and len(blocks_by_engine) > 1:
            exact = blocks_by_engine["digital-pymupdf"]
            for name, blocks in blocks_by_engine.items():
                if name == "digital-pymupdf":
                    all_blocks.extend(blocks)
                    continue
                kept, dropped = deduplicate_blocks(exact, blocks)
                page_result.deduplicated += len(dropped)
                all_blocks.extend(kept)
        else:
            for blocks in blocks_by_engine.values():
                all_blocks.extend(blocks)
        if len(blocks_by_engine) == 2:
            names = sorted(blocks_by_engine)
            page_result.disagreement = compare_engines(
                blocks_by_engine[names[0]], blocks_by_engine[names[1]]
            )
        page_result.blocks_by_engine = {
            name: len(blocks) for name, blocks in blocks_by_engine.items()
        }
        page_result.block_count = len(all_blocks)
        recorder.record_ocr_blocks(
            document_id=document_id,
            page_number=page_input.page_number,
            blocks=all_blocks,
        )
        _record_page_done(recorder, document_id, job_id, page_input, page_result, correlation_id)
        return page_result
    except Exception as exc:  # a page failure never fails the document
        page_result.error = f"ocr_failed: {exc}"
        _record_page_failure(
            recorder,
            document_id,
            job_id,
            page_input,
            "ocr_failed",
            page_result.error,
            correlation_id,
        )
        return page_result


def _record_page_done(
    recorder: StageRecorder,
    document_id: uuid.UUID,
    job_id: uuid.UUID | None,
    page_input: OcrPageInput,
    page_result: PageOcrResult,
    correlation_id: str | None,
) -> None:
    recorder.record(
        document_id=document_id,
        job_id=job_id,
        stage=PipelineStage.OCR_DONE,
        status="done",
        detail={
            "page_number": page_input.page_number,
            "engines_run": page_result.engines_run,
            "block_count": page_result.block_count,
            "deduplicated": page_result.deduplicated,
            "disagreement": page_result.disagreement,
        },
        correlation_id=correlation_id,
    )


def _record_page_failure(
    recorder: StageRecorder,
    document_id: uuid.UUID,
    job_id: uuid.UUID | None,
    page_input: OcrPageInput,
    error_code: str,
    message: str,
    correlation_id: str | None,
) -> None:
    recorder.record_error(
        document_id=document_id,
        job_id=job_id,
        page_number=page_input.page_number,
        stage=PipelineStage.OCR_DONE.value,
        error_code=error_code,
        message=message,
    )
    recorder.record(
        document_id=document_id,
        job_id=job_id,
        stage=PipelineStage.OCR_DONE,
        status="failed",
        detail={"page_number": page_input.page_number, "error_code": error_code},
        correlation_id=correlation_id,
    )
