# OfficerPath AI — PDF Engine (Phase 1, M2)
# PDF pipeline stage: analysis -> classification -> rendering ->
# quality measurement -> adaptive preprocessing, one page at a time.
#
# Wiring (prompt §5.3): this is a PIPELINE STAGE, not a request
# handler. The M1 upload endpoints still only validate + store +
# register; the worker (M7) calls run_pdf_stage for a stored
# document. Until M7 exists, run it from the CLI script
# (scripts/run_m2_pipeline.py) or from tests. Running it inline in
# the upload request would block the request and hold whole-document
# renders in memory — the reason it is deliberately NOT wired into
# the upload endpoints in M2.
#
# Stage discipline: transitions go through can_transition; a page
# failure is a ProcessingError row + a failed per-page stage record,
# and the document continues with the next page. The document-level
# stage after M2 is PREPROCESSING (done); the PREPROCESSING ->
# OCR_DONE transition belongs to M3 and is NOT claimed here.

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import cv2
import numpy as np

from app.config import Settings
from app.pipeline.ingestion.classifier import PageClassification, classify_pages
from app.pipeline.ingestion.service import StageRecorder
from app.pipeline.ingestion.validator import validate_file
from app.pipeline.interfaces import PipelineStage, can_transition
from app.pipeline.pdf.analysis import PageAnalysis, analyze_pdf
from app.pipeline.pdf.classifier import classify_pages_from_analysis
from app.pipeline.pdf.quality import PageQuality, measure_quality, png_to_bgr, png_to_gray
from app.pipeline.pdf.renderer import render_image_file, render_pdf_page
from app.pipeline.preprocess.marks import detect_highlight_regions
from app.pipeline.preprocess.preprocessor import ProcessedPage, process_page
from app.pipeline.preprocess.profiles import (
    PROFILE_VERSION,
    QualitySnapshot,
    select_profile,
)
from app.storage.base import StorageBackend
from app.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class PagePdfResult:
    """Outcome for ONE page of the PDF stage."""

    page_number: int
    classification: str
    classification_method: str
    profile_name: str
    profile_version: str
    quality_before: dict | None = None
    quality_after: dict | None = None
    render_width_px: int | None = None
    render_height_px: int | None = None
    render_dpi_used: float | None = None
    original_render_path: str | None = None
    processed_render_path: str | None = None
    highlight_regions: list[dict] = field(default_factory=list)
    profile_comparison: dict | None = None
    error: str | None = None


@dataclass
class DocumentPdfResult:
    """Outcome for one document's PDF stage."""

    document_id: uuid.UUID
    pages: list[PagePdfResult] = field(default_factory=list)
    pages_failed: int = 0

    @property
    def pages_processed(self) -> int:
        return len([p for p in self.pages if p.error is None])


def _store_png(storage: StorageBackend, document_id: uuid.UUID, name: str, png: bytes) -> str:
    """Store a render under the document's own directory. A UUID
    suffix keeps put() write-once semantics (no overwrite ever)."""
    path = f"{document_id}/{uuid.uuid4()}-{name}"
    storage.put(path, png)
    return path


def _encode_png(image: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("OpenCV could not encode the processed page as PNG.")
    return bytes(buffer)


def _choose_profile(settings: Settings, quality: PageQuality) -> tuple[str, str]:
    """Explicit profile from settings wins; otherwise auto-select
    from the measured quality."""
    if settings.preprocess_profile != "auto":
        return settings.preprocess_profile, "explicit profile from settings"
    snapshot = QualitySnapshot(
        blur_score=quality.blur_score,
        contrast_score=quality.contrast_score,
        noise_score=quality.noise_score,
        skew_degrees=quality.skew_degrees,
        ink_coverage=quality.ink_coverage,
    )
    return select_profile(snapshot)


def _is_low_quality(quality: PageQuality) -> bool:
    """A page worth a second-profile comparison (M2 rule). The
    thresholds match profiles.select_profile exactly — a page that
    selects anything but "clean" gets a second opinion. Blank pages
    are excluded: blur 0 would otherwise trigger a pointless (and
    expensive) second run on an empty page."""
    if quality.ink_coverage is not None and quality.ink_coverage < 0.005:
        return False
    return bool(
        (quality.blur_score is not None and quality.blur_score < 30)
        or (quality.contrast_score is not None and quality.contrast_score < 15)
        or (quality.noise_score is not None and quality.noise_score > 3)
        or (quality.skew_degrees is not None and abs(quality.skew_degrees) >= 0.5)
    )


def _process_one_page(
    *,
    document_id: uuid.UUID,
    page_number: int,
    classification: PageClassification,
    png_bytes: bytes,
    render_width_px: int,
    render_height_px: int,
    render_dpi_used: float,
    settings: Settings,
    storage: StorageBackend,
) -> PagePdfResult:
    """Render -> measure -> profile -> preprocess -> store. Pure
    per-page work; raises nothing — the caller records failures."""
    colour = png_to_bgr(png_bytes)
    gray = png_to_gray(png_bytes)
    quality_before = measure_quality(gray)
    profile_name, reason = _choose_profile(settings, quality_before)
    original_path = _store_png(storage, document_id, f"page-{page_number}-original.png", png_bytes)
    highlights = detect_highlight_regions(colour)
    processed = process_page(
        colour,
        profile_name,
        quality_before=quality_before,
        max_pixels=settings.max_render_pixels,
    )
    comparison: dict | None = None
    chosen = processed
    if settings.preprocess_compare_second_profile and _is_low_quality(quality_before):
        # Second opinion on a bad page: run the other candidate and
        # keep whichever scores better on contrast + sharpness without
        # collapsing the ink. The comparison is recorded, never hidden.
        second_name = "low_quality" if profile_name != "low_quality" else "default"
        second = process_page(
            colour,
            second_name,
            quality_before=quality_before,
            max_pixels=settings.max_render_pixels,
        )
        first_score = _profile_score(processed)
        second_score = _profile_score(second)
        comparison = {
            "first_profile": profile_name,
            "first_score": round(first_score, 3),
            "second_profile": second_name,
            "second_score": round(second_score, 3),
            "chosen": profile_name if first_score >= second_score else second_name,
            "reason": "low-quality page: two profiles compared",
        }
        if second_score > first_score:
            chosen = second
            profile_name = second_name
    processed_path = _store_png(
        storage,
        document_id,
        f"page-{page_number}-processed.png",
        _encode_png(chosen.gray),
    )
    record = chosen.to_record()
    record["selection_reason"] = reason
    if comparison is not None:
        record["profile_comparison"] = comparison
    return PagePdfResult(
        page_number=page_number,
        classification=classification.classification,
        classification_method=classification.method,
        profile_name=profile_name,
        profile_version=PROFILE_VERSION,
        quality_before=quality_before.to_dict(),
        quality_after=chosen.quality_after.to_dict() if chosen.quality_after else None,
        render_width_px=render_width_px,
        render_height_px=render_height_px,
        render_dpi_used=render_dpi_used,
        original_render_path=original_path,
        processed_render_path=processed_path,
        highlight_regions=highlights,
        profile_comparison=comparison,
    )


def _profile_score(processed: ProcessedPage) -> float:
    """Comparison score for two profiles on the same page: contrast
    gain + sharpness, penalised if the ink collapses (a blank-looking
    page is not a 'better' page). All terms are measured, not tuned
    to any fixture."""
    before = processed.quality_before
    after = processed.quality_after
    if before is None or after is None:
        return 0.0
    contrast_gain = (after.contrast_score or 0.0) - (before.contrast_score or 0.0)
    blur = after.blur_score or 0.0
    ink_before = before.ink_coverage or 0.0
    ink_after = after.ink_coverage or 0.0
    ink_ratio = (ink_after / ink_before) if ink_before > 0 else 1.0
    if ink_ratio < 0.5:
        return -1.0  # ink collapse: this profile destroyed content
    return contrast_gain + min(blur, 200.0) / 10.0


def run_pdf_stage(
    *,
    document_id: uuid.UUID,
    job_id: uuid.UUID | None,
    filename: str,
    data: bytes,
    settings: Settings,
    storage: StorageBackend,
    recorder: StageRecorder,
    correlation_id: str | None = None,
    current_stage: PipelineStage = PipelineStage.QUEUED,
) -> DocumentPdfResult:
    """Run the M2 PDF stage for one stored document.

    Raises ValueError when the current stage cannot transition to
    PREPROCESSING (fail loudly — a stage must never run out of order).
    Per-page failures are recorded, never raised.
    """
    correlation = correlation_id or str(uuid.uuid4())
    if not can_transition(current_stage, PipelineStage.PREPROCESSING):
        raise ValueError(
            f"Cannot run the PDF stage from stage {current_stage.value!r}: "
            "the state machine does not allow this transition."
        )
    recorder.record(
        document_id=document_id,
        job_id=job_id,
        stage=PipelineStage.PREPROCESSING,
        status="started",
        detail={"filename": filename},
        correlation_id=correlation,
    )
    report = validate_file(filename, data, settings)
    result = DocumentPdfResult(document_id=document_id)
    ext = report.extension
    if ext == "pdf":
        try:
            analysis = analyze_pdf(data)
            classifications = classify_pages_from_analysis(analysis.pages)
        except ValueError as exc:
            recorder.record_error(
                document_id=document_id,
                job_id=job_id,
                page_number=None,
                stage=PipelineStage.PREPROCESSING.value,
                error_code="pdf_analysis_failed",
                message=str(exc),
            )
            recorder.record(
                document_id=document_id,
                job_id=job_id,
                stage=PipelineStage.PREPROCESSING,
                status="failed",
                detail={"error": str(exc)},
                correlation_id=correlation,
            )
            return result
        for page in analysis.pages:
            classification = classifications[page.page_number - 1]
            try:
                rendered = render_pdf_page(
                    data,
                    page.page_number,
                    dpi=settings.render_dpi,
                    max_pixels=settings.max_render_pixels,
                )
                page_result = _process_one_page(
                    document_id=document_id,
                    page_number=page.page_number,
                    classification=classification,
                    png_bytes=rendered.png_bytes,
                    render_width_px=rendered.width_px,
                    render_height_px=rendered.height_px,
                    render_dpi_used=rendered.dpi_used,
                    settings=settings,
                    storage=storage,
                )
                result.pages.append(page_result)
                _record_page(recorder, document_id, job_id, page, page_result, correlation)
            except Exception as exc:  # one bad page never fails the document
                result.pages_failed += 1
                result.pages.append(
                    PagePdfResult(
                        page_number=page.page_number,
                        classification=classification.classification,
                        classification_method=classification.method,
                        profile_name="",
                        profile_version=PROFILE_VERSION,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
                recorder.record_error(
                    document_id=document_id,
                    job_id=job_id,
                    page_number=page.page_number,
                    stage=PipelineStage.PREPROCESSING.value,
                    error_code="page_processing_failed",
                    message=str(exc),
                    detail={"classification": classification.classification},
                )
                log.info(
                    "pdf stage page failed, continuing",
                    extra={
                        "fields": {
                            "document_id": str(document_id),
                            "page_number": page.page_number,
                            "correlation_id": correlation,
                        }
                    },
                )
    elif ext in ("jpg", "jpeg", "png", "webp", "tiff", "tif"):
        pages = classify_pages(report, data=data)
        classification = (
            pages[0]
            if pages
            else PageClassification(
                page_number=1, classification="unknown", method="none", confidence=None
            )
        )
        try:
            rendered = render_image_file(
                data, dpi=settings.render_dpi, max_pixels=settings.max_render_pixels
            )
            page_result = _process_one_page(
                document_id=document_id,
                page_number=1,
                classification=classification,
                png_bytes=rendered.png_bytes,
                render_width_px=rendered.width_px,
                render_height_px=rendered.height_px,
                render_dpi_used=rendered.dpi_used,
                settings=settings,
                storage=storage,
            )
            result.pages.append(page_result)
            recorder.record(
                document_id=document_id,
                job_id=job_id,
                stage=PipelineStage.PREPROCESSING,
                status="done",
                detail={"page_number": 1, "profile": page_result.profile_name},
                correlation_id=correlation,
            )
        except Exception as exc:
            result.pages_failed += 1
            result.pages.append(
                PagePdfResult(
                    page_number=1,
                    classification=classification.classification,
                    classification_method=classification.method,
                    profile_name="",
                    profile_version=PROFILE_VERSION,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            recorder.record_error(
                document_id=document_id,
                job_id=job_id,
                page_number=1,
                stage=PipelineStage.PREPROCESSING.value,
                error_code="page_processing_failed",
                message=str(exc),
            )
    else:
        # txt/docx: no pages to render in M2. Classification from M1
        # stands; the PDF stage records that honestly and finishes.
        for classified in classify_pages(report, data=data):
            result.pages.append(
                PagePdfResult(
                    page_number=classified.page_number,
                    classification=classified.classification,
                    classification_method=classified.method,
                    profile_name="",
                    profile_version=PROFILE_VERSION,
                    error=None,
                )
            )
        log.info(
            "pdf stage skipped rendering for text document",
            extra={"fields": {"document_id": str(document_id), "extension": ext}},
        )
    recorder.record(
        document_id=document_id,
        job_id=job_id,
        stage=PipelineStage.PREPROCESSING,
        status="done" if result.pages_failed == 0 else "failed",
        detail={
            "pages_processed": result.pages_processed,
            "pages_failed": result.pages_failed,
            "profiles": sorted({p.profile_name for p in result.pages if p.profile_name}),
        },
        correlation_id=correlation,
    )
    return result


def _record_page(
    recorder: StageRecorder,
    document_id: uuid.UUID,
    job_id: uuid.UUID | None,
    page: PageAnalysis,
    page_result: PagePdfResult,
    correlation: str | None,
) -> None:
    """Persist one page's M2 facts (metrics + render paths + profile)
    and its per-page stage row. recorder.update_page is a no-op when
    no page row exists (Null recorder logs only)."""
    recorder.update_page(
        document_id,
        page.page_number,
        classification=page_result.classification,
        classification_method=page_result.classification_method,
        width_px=page_result.render_width_px,
        height_px=page_result.render_height_px,
        dpi_estimate=page_result.render_dpi_used,
        has_text_layer=page.has_text_layer,
        skew_degrees=(
            page_result.quality_before.get("skew_degrees") if page_result.quality_before else None
        ),
        blur_score=(
            page_result.quality_before.get("blur_score") if page_result.quality_before else None
        ),
        noise_score=(
            page_result.quality_before.get("noise_score") if page_result.quality_before else None
        ),
        contrast_score=(
            page_result.quality_before.get("contrast_score") if page_result.quality_before else None
        ),
        original_render_path=page_result.original_render_path,
        processed_render_path=page_result.processed_render_path,
        preprocessing_applied={
            "profile": page_result.profile_name,
            "profile_version": page_result.profile_version,
            "quality_before": page_result.quality_before,
            "quality_after": page_result.quality_after,
            "highlight_regions": page_result.highlight_regions,
            "profile_comparison": page_result.profile_comparison,
        },
    )
    recorder.record(
        document_id=document_id,
        job_id=job_id,
        stage=PipelineStage.PREPROCESSING,
        status="done",
        detail={
            "page_number": page.page_number,
            "classification": page_result.classification,
            "profile": page_result.profile_name,
        },
        correlation_id=correlation,
    )
