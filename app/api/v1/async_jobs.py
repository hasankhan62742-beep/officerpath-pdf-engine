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
from app.workers.processor import cancel_job, get_job_status, retry_job

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
    try:
        document_id = uuid.uuid4()
        job_id = uuid.uuid4()
        storage_path = f"{user['id']}/async/{job_id}.{ext}"
        _storage_backend().put(storage_path, data)
        document = db.Document(
            id=document_id,
            user_id=uuid.UUID(user["id"]),
            title=file.filename or f"upload.{ext}",
            storage_path=storage_path,
            file_type=file_type,
            file_size_bytes=len(data),
            page_count=None,
            content_hash=hashlib.sha256(data).hexdigest(),
        )
        session.add(document)
        session.flush()
        job = db.Job(
            id=job_id,
            user_id=uuid.UUID(user["id"]),
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
            detail={"filename": file.filename or f"upload.{ext}"},
        )
        session.commit()
    finally:
        session.close()
    return AsyncJobCreatedResponse(
        job_id=str(job_id),
        document_id=str(document_id),
        status="queued",
        filename=file.filename or f"upload.{ext}",
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
