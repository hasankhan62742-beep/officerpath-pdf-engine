# OfficerPath AI — PDF Engine (Phase 1, M1)
# Ingestion service: validate -> SHA-256 dedup -> store (immutable) ->
# register document + job -> record stage history.
#
# Order matters: a file is never stored or registered before it
# validates, and a duplicate (same user + same SHA-256) never creates
# a second document or job — the original is returned instead
# (idempotent re-upload, prompt §6). A rejected file produces a
# per-file result with machine-readable reasons; in a batch, one bad
# file never blocks the others.
#
# Stage history is written through a StageRecorder. When DATABASE_URL
# is configured the SQLAlchemy recorder persists processing_stages
# rows; otherwise the Null recorder keeps the run honest in logs only.
# The service never invents a stage it did not perform.

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.config import Settings
from app.database.repositories import DocumentRepository, JobRepository
from app.db.models import DocumentPage, ProcessingError, ProcessingStage
from app.db.models import OCRBlock as OCRBlockRow
from app.pipeline.ingestion.classifier import PageClassification, classify_pages
from app.pipeline.ingestion.validator import (
    ValidationIssue,
    ValidationReport,
    validate_file,
)
from app.pipeline.interfaces import OCRBlock, PipelineStage
from app.schemas.documents import DocumentRegisterRequest
from app.services import jobs as job_service
from app.storage.base import StorageBackend, safe_storage_name
from app.utils.logging import get_logger

log = get_logger(__name__)


class StageRecorder(Protocol):
    """Persist one pipeline-stage transition (prompt §5.3).

    M2 extends the protocol with the page-level operations the PDF
    stage needs: update_page (metrics / render paths on a
    document_pages row) and record_error (a failed page, recorded
    without failing the document). M3 adds record_ocr_blocks (the
    OCR stage persists every engine's blocks verbatim — originals
    are never edited after insert). Both recorders implement all
    methods; the Null recorder logs, the SQLAlchemy one persists."""

    def record(
        self,
        *,
        document_id: uuid.UUID,
        job_id: uuid.UUID | None,
        stage: PipelineStage,
        status: str,
        detail: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None: ...

    def update_page(
        self,
        document_id: uuid.UUID,
        page_number: int,
        **fields: Any,
    ) -> None: ...

    def record_error(
        self,
        *,
        document_id: uuid.UUID,
        job_id: uuid.UUID | None,
        page_number: int | None,
        stage: str,
        error_code: str,
        message: str,
        detail: dict[str, Any] | None = None,
    ) -> None: ...

    def record_ocr_blocks(
        self,
        *,
        document_id: uuid.UUID,
        page_number: int,
        blocks: list[OCRBlock],
    ) -> None: ...


class NullStageRecorder:
    """No database configured: record stages in logs only."""

    def record(
        self,
        *,
        document_id: uuid.UUID,
        job_id: uuid.UUID | None,
        stage: PipelineStage,
        status: str,
        detail: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        log.info(
            "pipeline stage (no database configured)",
            extra={
                "fields": {
                    "document_id": str(document_id),
                    "job_id": str(job_id) if job_id else None,
                    "stage": stage.value,
                    "status": status,
                    "correlation_id": correlation_id,
                }
            },
        )

    def update_page(
        self,
        document_id: uuid.UUID,
        page_number: int,
        **fields: Any,
    ) -> None:
        """No database configured: page metrics are log-only."""
        log.info(
            "pipeline page update (no database configured)",
            extra={
                "fields": {
                    "document_id": str(document_id),
                    "page_number": page_number,
                    "fields": sorted(fields),
                }
            },
        )

    def record_error(
        self,
        *,
        document_id: uuid.UUID,
        job_id: uuid.UUID | None,
        page_number: int | None,
        stage: str,
        error_code: str,
        message: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        """No database configured: page failures are log-only."""
        log.info(
            "pipeline page error (no database configured)",
            extra={
                "fields": {
                    "document_id": str(document_id),
                    "page_number": page_number,
                    "stage": stage,
                    "error_code": error_code,
                    "message": message,
                }
            },
        )

    def record_ocr_blocks(
        self,
        *,
        document_id: uuid.UUID,
        page_number: int,
        blocks: list[OCRBlock],
    ) -> None:
        """No database configured: OCR blocks are log-only (count +
        engines). The blocks themselves are returned to the caller;
        nothing is persisted."""
        log.info(
            "pipeline ocr blocks (no database configured)",
            extra={
                "fields": {
                    "document_id": str(document_id),
                    "page_number": page_number,
                    "block_count": len(blocks),
                    "engines": sorted({block.engine for block in blocks}),
                }
            },
        )


class SqlAlchemyStageRecorder:
    """Persist stage transitions + page rows to processing_stages /
    document_pages (Alembic 0001 tables)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def record(
        self,
        *,
        document_id: uuid.UUID,
        job_id: uuid.UUID | None,
        stage: PipelineStage,
        status: str,
        detail: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        row = ProcessingStage(
            document_id=document_id,
            job_id=job_id,
            stage=stage.value,
            status=status,
            detail=detail,
            correlation_id=correlation_id,
        )
        self._session.add(row)
        self._session.commit()

    def close(self) -> None:
        self._session.close()

    def update_page(
        self,
        document_id: uuid.UUID,
        page_number: int,
        **fields: Any,
    ) -> None:
        """Update one document_pages row (M2 metrics / render paths).
        Silently no-ops when the row does not exist yet (the M2
        pipeline creates page rows first via record_pages)."""
        row = (
            self._session.query(DocumentPage)
            .filter_by(document_id=document_id, page_number=page_number)
            .one_or_none()
        )
        if row is None:
            return
        for key, value in fields.items():
            if hasattr(row, key):
                setattr(row, key, value)
        self._session.commit()

    def record_error(
        self,
        *,
        document_id: uuid.UUID,
        job_id: uuid.UUID | None,
        page_number: int | None,
        stage: str,
        error_code: str,
        message: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        """Persist one page-level failure (prompt §2: a failed page
        never fails the whole document silently)."""
        self._session.add(
            ProcessingError(
                document_id=document_id,
                job_id=job_id,
                page_number=page_number,
                stage=stage,
                error_code=error_code,
                message=message,
                detail=detail,
            )
        )
        self._session.commit()

    def record_ocr_blocks(
        self,
        *,
        document_id: uuid.UUID,
        page_number: int,
        blocks: list[OCRBlock],
    ) -> None:
        """Persist OCR blocks verbatim (one row per block, original
        engine output — never edited after insert). The page_id is
        resolved from the document_pages row when it exists; the
        blocks are still stored when it does not (page_id NULL)."""
        page_row = (
            self._session.query(DocumentPage)
            .filter_by(document_id=document_id, page_number=page_number)
            .one_or_none()
        )
        for block in blocks:
            bbox = block.bbox
            self._session.add(
                OCRBlockRow(
                    document_id=document_id,
                    page_id=page_row.id if page_row is not None else None,
                    page_number=page_number,
                    engine=block.engine,
                    engine_version=block.engine_version,
                    language=block.language,
                    text=block.text,
                    bbox_x_min=bbox.x_min if bbox else None,
                    bbox_y_min=bbox.y_min if bbox else None,
                    bbox_x_max=bbox.x_max if bbox else None,
                    bbox_y_max=bbox.y_max if bbox else None,
                    reading_order=block.reading_order,
                    confidence=block.confidence,
                    word_confidences=block.word_confidences,
                    style=block.style,
                )
            )
        self._session.commit()

    def record_pages(self, document_id: uuid.UUID, pages: list[PageClassification]) -> None:
        for page in pages:
            self._session.add(
                DocumentPage(
                    document_id=document_id,
                    page_number=page.page_number,
                    classification=page.classification,
                    classification_method=page.method,
                    classification_confidence=page.confidence,
                    width_px=page.width_px,
                    height_px=page.height_px,
                    dpi_estimate=page.dpi_estimate,
                    rotation_degrees=page.rotation_degrees,
                )
            )
        self._session.commit()


@dataclass
class IngestionOutcome:
    """Result for ONE file. status: stored | replay | rejected."""

    status: str
    filename: str
    report: ValidationReport
    pages: list[PageClassification] = field(default_factory=list)
    document: dict[str, Any] | None = None
    job: dict[str, Any] | None = None
    storage_path: str | None = None
    idempotent_replay: bool = False


def ingest_file(
    *,
    user: dict,
    filename: str,
    data: bytes,
    settings: Settings,
    storage: StorageBackend,
    documents: DocumentRepository,
    jobs: JobRepository,
    recorder: StageRecorder,
    correlation_id: str | None = None,
) -> IngestionOutcome:
    """Ingest one file end to end. Never raises for a bad file: the
    rejection is the returned outcome (the API maps it to 422 / a
    per-file batch entry). Storage/DB errors still raise — those are
    server failures, not file failures, and must surface loudly."""
    user_id = user["id"]
    correlation = correlation_id or str(uuid.uuid4())
    report = validate_file(filename, data, settings)
    if not report.valid:
        log.info(
            "ingestion rejected file",
            extra={
                "fields": {
                    "user_id": user_id,
                    "filename": filename,
                    "codes": [i.code for i in report.errors],
                    "correlation_id": correlation,
                }
            },
        )
        return IngestionOutcome(status="rejected", filename=filename, report=report)

    # M2: pass the raw bytes so PDFs get exact PyMuPDF classification;
    # without them the M1 byte heuristic is the fallback.
    pages = classify_pages(report, data=data)

    # SHA-256 dedup (per user — never reveal another user's file).
    existing = documents.find_by_user_and_sha256(user_id, report.sha256)
    if existing is not None:
        existing_job = jobs.find_by_document_id(existing["id"])
        if existing_job is not None:
            log.info(
                "ingestion dedup replay",
                extra={
                    "fields": {
                        "user_id": user_id,
                        "document_id": existing["id"],
                        "sha256": report.sha256,
                        "correlation_id": correlation,
                    }
                },
            )
            return IngestionOutcome(
                status="replay",
                filename=filename,
                report=report,
                pages=pages,
                document=existing,
                job=existing_job,
                storage_path=existing.get("storage_path"),
                idempotent_replay=True,
            )

    # Store first (immutable, write-once), then register. If the
    # register fails after storing, the stored file is orphaned but
    # harmless: same content re-uploaded later dedups by hash only
    # after registration, so an orphan is re-stored under a new UUID
    # name — a known M1 wart, fixed by a reaper in M7.
    storage_path = safe_storage_name(user_id, filename)
    storage.put(storage_path, data)

    payload = DocumentRegisterRequest(
        title=filename,
        storage_path=storage_path,
        file_type=report.extension,  # type: ignore[arg-type]
        file_size_bytes=report.size_bytes,
        page_count=report.pdf_page_count_estimate
        if report.extension == "pdf"
        else (len(pages) if pages else None),
        content_hash=report.sha256,
        metadata={
            "classification": [p.classification for p in pages],
            "classification_method": pages[0].method if pages else None,
            "pdf_encrypted": report.pdf_encrypted,
            "decompression_ratio": report.decompression_ratio,
            "warnings": [w.code for w in report.warnings],
        },
    )
    document, job, _replay = job_service.register_document(user, payload, documents, jobs)
    document_id = uuid.UUID(document["id"])
    job_id = uuid.UUID(job["id"])
    recorder.record(
        document_id=document_id,
        job_id=job_id,
        stage=PipelineStage.UPLOADED,
        status="done",
        detail={"storage_path": storage_path, "sha256": report.sha256},
        correlation_id=correlation,
    )
    recorder.record(
        document_id=document_id,
        job_id=job_id,
        stage=PipelineStage.VALIDATED,
        status="done",
        detail={
            "page_count_estimate": report.pdf_page_count_estimate,
            "classification": [p.classification for p in pages],
        },
        correlation_id=correlation,
    )
    recorder.record(
        document_id=document_id,
        job_id=job_id,
        stage=PipelineStage.QUEUED,
        status="done",
        detail={},
        correlation_id=correlation,
    )
    if isinstance(recorder, SqlAlchemyStageRecorder):
        recorder.record_pages(document_id, pages)
    return IngestionOutcome(
        status="stored",
        filename=filename,
        report=report,
        pages=pages,
        document=document,
        job=job,
        storage_path=storage_path,
    )


def ingest_batch(
    *,
    user: dict,
    files: list[tuple[str, bytes]],
    settings: Settings,
    storage: StorageBackend,
    documents: DocumentRepository,
    jobs: JobRepository,
    recorder: StageRecorder,
    correlation_id: str | None = None,
) -> list[IngestionOutcome]:
    """Batch upload: each file is independent. One bad file never
    blocks the batch; storage/DB errors on one file are caught and
    reported as that file's rejection with code `ingestion_failed`
    (the server error is logged with the correlation id)."""
    outcomes: list[IngestionOutcome] = []
    for filename, data in files:
        try:
            outcomes.append(
                ingest_file(
                    user=user,
                    filename=filename,
                    data=data,
                    settings=settings,
                    storage=storage,
                    documents=documents,
                    jobs=jobs,
                    recorder=recorder,
                    correlation_id=correlation_id,
                )
            )
        except Exception as exc:  # server-side failure for this file only
            log.exception(
                "batch ingestion failed for one file",
                extra={"fields": {"filename": filename, "correlation_id": correlation_id}},
            )
            report = validate_file(filename, data, settings)
            report.issues.append(
                ValidationIssue(
                    "ingestion_failed",
                    f"Server could not ingest this file: {type(exc).__name__}.",
                )
            )
            outcomes.append(IngestionOutcome(status="rejected", filename=filename, report=report))
    return outcomes
