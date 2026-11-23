# OfficerPath AI — PDF Engine (Phase 1, M7)
# Async-jobs API: submit a document for BACKGROUND processing and
# poll it. The upload returns 202 immediately with a queued job;
# the worker (app/workers) does the parse. This is the path the
# Flutter app should use for large uploads: the synchronous parse
# endpoint blocks the request for the whole OCR run (~130 s for
# PPSC-66 on the VM), while this one returns at once.
#
# POST /api/v1/async-jobs/parse — multipart PDF (or JPEG/PNG),
#   stored under <user_id>/async/<job_id>.<ext>, Document + Job
#   rows created (status queued), 202 + job id.
# GET /api/v1/async-jobs/{job_id} — job + stage history + result
#   summary (per-user; 404 for unknown/other-user jobs).
# POST /api/v1/async-jobs/{job_id}/cancel — queued -> cancelled
#   now; processing -> flagged, cancelled at the next stage
#   boundary; anything else -> 409.
# POST /api/v1/async-jobs/{job_id}/retry — failed/cancelled ->
#   queued again (retry_count+1); anything else -> 409.
#
# All four are per-user (404, never leak existence) and rate
# limited. A job whose bytes cannot be found fails in the worker
# with "no stored bytes" — never silently.

import hashlib
import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.core.errors import ApiError
from app.db import models as db
from app.db.session import get_session
from app.pipeline.ingestion.service import SqlAlchemyStageRecorder
from app.pipeline.interfaces import PipelineStage
from app.pipeline.matching.service import IMAGE_MAGIC
from app.schemas.async_jobs import (
    AsyncJobCreatedResponse,
    AsyncJobStageResponse,
    AsyncJobStatusResponse,
)
from app.security.dependencies import get_current_user
from app.security.rate_limit import rate_limiter
from app.storage.local import LocalDiskStorage
from app.utils.logging import get_logger
from app.workers.processor import cancel_job, get_job_status, retry_job

log = get_logger(__name__)

router = APIRouter(prefix="/api/v1/async-jobs", tags=["async-jobs"])

PDF_MAGIC = b"%PDF"


def _session_or_503():
    session = get_session()
    if session is None:
        raise ApiError(
            status_code=503,
            code="database_unavailable",
            message="The database is not configured on this server.",
        )
    return session


def _storage_backend():
    if settings.storage_backend != "local":
        raise ApiError(
            status_code=503,
            code="storage_unavailable",
            message=f"Storage backend {settings.storage_backend!r} is not configured.",
        )
    return LocalDiskStorage(settings.storage_root)


def _job_uuid(job_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(job_id)
    except ValueError:
        raise ApiError(status_code=404, code="not_found", message="Job not found.") from None


@router.post("/parse", response_model=AsyncJobCreatedResponse, status_code=202)
def submit_async_parse(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> AsyncJobCreatedResponse:
    rate_limiter.check(
        f"parse:{user['id']}",
        settings.rate_limit_register_per_minute,
        settings.rate_limit_window_seconds,
    )
    data = file.file.read()
    if len(data) > settings.max_file_size_bytes:
        raise ApiError(
            status_code=422,
            code="file_too_large",
            message=f"File is {len(data)} bytes; limit is {settings.max_file_size_bytes}.",
        )
    if data.startswith(PDF_MAGIC):
        file_type, ext = "pdf", "pdf"
    elif data.startswith(IMAGE_MAGIC):
        file_type, ext = ("png", "png") if data.startswith(b"\x89PNG") else ("jpg", "jpg")
    else:
        raise ApiError(
            status_code=422,
            code="invalid_file",
            message="Upload must be a PDF, JPEG, or PNG file.",
        )
    session = _session_or_503()
    content_hash = hashlib.sha256(data).hexdigest()
    user_uuid = uuid.UUID(user["id"])
    filename = file.filename or f"upload.{ext}"
    # M10 — idempotent replay (M7 edge, fixed here): the same user
    # re-submitting the same bytes used to 500 with UNIQUE constraint
    # failed on documents.user_id + content_hash, because this path
    # never got the dedup check the register/upload path has (M6).
    # Decision — replay returns the ORIGINAL job, consistent with the
    # register contract (POST /api/v1/documents/register answers 200
    # + idempotent_replay on replay, 201 on a fresh registration):
    # the bytes are identical, the worker reads them from the
    # document's storage_path, so the existing job IS the job for
    # these bytes; a 409/422 would force every client to implement a
    # lookup dance and would break retry-on-failure flows. A replay
    # answers 200 (nothing new was created); a fresh submit answers
    # 202. Soft-deleted documents never block a replay — the lookup
    # ignores them, matching the M6 partial-unique-index rule, so
    # delete-then-re-upload of the same file creates a fresh job.
    existing = (
        session.query(db.Document)
        .filter(
            db.Document.user_id == user_uuid,
            db.Document.content_hash == content_hash,
            db.Document.deleted_at.is_(None),
        )
        .first()
    )
    if existing is not None:
        job = (
            session.query(db.Job)
            .filter(db.Job.document_id == existing.id)
            .order_by(db.Job.created_at.desc())
            .first()
        )
        if job is None:
            # A live document without a job is a partial write (both
            # endpoints create document + job in one transaction, so
            # this cannot happen on the happy path). Mirror the
            # register path: a server error, never a new job.
            session.close()
            raise ApiError(
                status_code=500,
                code="internal_error",
                message="An unexpected error occurred.",
            )
        log.info(
            "Idempotent replay of async parse; returning original job",
            extra={"fields": {"user_id": user["id"], "job_id": str(job.id)}},
        )
        response = AsyncJobCreatedResponse(
            job_id=str(job.id),
            document_id=str(existing.id),
            status=job.status,
            filename=existing.title,
            idempotent_replay=True,
        )
        session.close()
        return JSONResponse(status_code=200, content=response.model_dump())
    try:
        document_id = uuid.uuid4()
        job_id = uuid.uuid4()
        storage_path = f"{user['id']}/async/{job_id}.{ext}"
        _storage_backend().put(storage_path, data)
        document = db.Document(
            id=document_id,
            user_id=user_uuid,
            title=filename,
            storage_path=storage_path,
            file_type=file_type,
            file_size_bytes=len(data),
            page_count=None,
            content_hash=content_hash,
        )
        session.add(document)
        try:
            session.flush()
        except IntegrityError:
            # Race guard: two identical submits in flight can both
            # pass the lookup above; the partial unique index lets
            # exactly one win. Roll back and re-read — the loser
            # answers with the winner's job instead of a 500.
            session.rollback()
            winner = (
                session.query(db.Document)
                .filter(
                    db.Document.user_id == user_uuid,
                    db.Document.content_hash == content_hash,
                    db.Document.deleted_at.is_(None),
                )
                .first()
            )
            if winner is None:
                raise
            winner_job = (
                session.query(db.Job)
                .filter(db.Job.document_id == winner.id)
                .order_by(db.Job.created_at.desc())
                .first()
            )
            if winner_job is None:
                raise
            log.info(
                "Async parse race resolved to the winning job",
                extra={"fields": {"user_id": user["id"], "job_id": str(winner_job.id)}},
            )
            response = AsyncJobCreatedResponse(
                job_id=str(winner_job.id),
                document_id=str(winner.id),
                status=winner_job.status,
                filename=winner.title,
                idempotent_replay=True,
            )
            session.close()
            return JSONResponse(status_code=200, content=response.model_dump())
        job = db.Job(
            id=job_id,
            user_id=user_uuid,
            document_id=document.id,
            status="queued",
        )
        session.add(job)
        session.flush()
        SqlAlchemyStageRecorder(session).record(
            document_id=document.id,
            job_id=job.id,
            stage=PipelineStage.QUEUED,
            status="done",
            detail={"filename": filename},
        )
        session.commit()
    finally:
        session.close()
    return AsyncJobCreatedResponse(
        job_id=str(job_id),
        document_id=str(document_id),
        status="queued",
        filename=filename,
    )


@router.get("/{job_id}", response_model=AsyncJobStatusResponse)
def async_job_status(
    job_id: str,
    user: dict = Depends(get_current_user),
) -> AsyncJobStatusResponse:
    session = _session_or_503()
    try:
        status = get_job_status(session, job_id=_job_uuid(job_id), user_id=user["id"])
    finally:
        session.close()
    return AsyncJobStatusResponse(
        **{**status, "stages": [AsyncJobStageResponse(**s) for s in status["stages"]]}
    )


@router.post("/{job_id}/cancel", response_model=AsyncJobStatusResponse)
def async_job_cancel(
    job_id: str,
    user: dict = Depends(get_current_user),
) -> AsyncJobStatusResponse:
    rate_limiter.check(
        f"retry:{user['id']}",
        settings.rate_limit_retry_per_minute,
        settings.rate_limit_window_seconds,
    )
    session = _session_or_503()
    try:
        cancel_job(session, job_id=_job_uuid(job_id), user_id=user["id"])
        status = get_job_status(session, job_id=_job_uuid(job_id), user_id=user["id"])
    finally:
        session.close()
    return AsyncJobStatusResponse(
        **{**status, "stages": [AsyncJobStageResponse(**s) for s in status["stages"]]}
    )


@router.post("/{job_id}/retry", response_model=AsyncJobStatusResponse)
def async_job_retry(
    job_id: str,
    user: dict = Depends(get_current_user),
) -> AsyncJobStatusResponse:
    rate_limiter.check(
        f"retry:{user['id']}",
        settings.rate_limit_retry_per_minute,
        settings.rate_limit_window_seconds,
    )
    session = _session_or_503()
    try:
        retry_job(session, job_id=_job_uuid(job_id), user_id=user["id"])
        status = get_job_status(session, job_id=_job_uuid(job_id), user_id=user["id"])
    finally:
        session.close()
    return AsyncJobStatusResponse(
        **{**status, "stages": [AsyncJobStageResponse(**s) for s in status["stages"]]}
    )
