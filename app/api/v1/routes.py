# OfficerPath AI — PDF Engine (Phase 1, M1)
# /api/v1 routes: document registration, file upload (single + batch),
# job status, job retry.
# All routes require a valid Supabase JWT (Authorization: Bearer <token>).
#
# Upload semantics (M1): POST /documents/upload validates the file
# bytes, stores the original immutably, dedups by SHA-256, and
# registers document + job. A rejected file answers 422 with the
# standard error envelope (code = first validation issue; the message
# lists every issue code). The batch endpoint answers 200 with a
# per-file result for every file — including rejections — so one bad
# file never blocks the batch and no file is silently skipped.

from contextlib import contextmanager

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.errors import ApiError
from app.database.sqlalchemy_repositories import (
    SqlAlchemyDocumentRepository,
    SqlAlchemyJobRepository,
)
from app.db.session import get_session
from app.pipeline.ingestion.service import (
    NullStageRecorder,
    SqlAlchemyStageRecorder,
    StageRecorder,
    ingest_batch,
    ingest_file,
)
from app.schemas.documents import (
    BatchUploadResponse,
    DocumentRegisterRequest,
    DocumentResponse,
    JobResponse,
    PageClassificationResponse,
    RegisterResponse,
    UploadResponse,
    ValidationIssueResponse,
)
from app.security.dependencies import get_current_user
from app.security.rate_limit import rate_limiter
from app.services import jobs as job_service
from app.storage.base import StorageBackend
from app.storage.local import LocalDiskStorage

router = APIRouter(prefix="/api/v1", tags=["v1"])

BATCH_MAX_FILES = 20


def _storage_backend() -> StorageBackend:
    if settings.storage_backend != "local":
        raise ApiError(
            status_code=503,
            code="storage_unavailable",
            message=f"Storage backend {settings.storage_backend!r} is not configured.",
        )
    return LocalDiskStorage(settings.storage_root)


def _stage_recorder() -> StageRecorder:
    """SQLAlchemy recorder when DATABASE_URL is set, else the null one.
    The caller closes the recorder when it is a SqlAlchemyStageRecorder
    (see _close_recorder)."""
    session = get_session()
    if session is None:
        return NullStageRecorder()
    return SqlAlchemyStageRecorder(session)


def _close_recorder(recorder: StageRecorder) -> None:
    if isinstance(recorder, SqlAlchemyStageRecorder):
        recorder.close()


def _upload_response(outcome) -> UploadResponse:
    return UploadResponse(
        status=outcome.status,
        filename=outcome.filename,
        document=DocumentResponse(**outcome.document) if outcome.document is not None else None,
        job=JobResponse(**outcome.job) if outcome.job is not None else None,
        storage_path=outcome.storage_path,
        idempotent_replay=outcome.idempotent_replay,
        sha256=outcome.report.sha256,
        pages=[
            PageClassificationResponse(
                page_number=p.page_number,
                classification=p.classification,
                method=p.method,
                confidence=p.confidence,
                width_px=p.width_px,
                height_px=p.height_px,
                dpi_estimate=p.dpi_estimate,
                rotation_degrees=p.rotation_degrees,
                note=p.note,
            )
            for p in outcome.pages
        ],
        issues=[
            ValidationIssueResponse(code=i.code, message=i.message, severity=i.severity)
            for i in outcome.report.issues
        ],
    )


@contextmanager
def _repositories():
    """Engine-DB repositories for one request (ADR-011). The engine
    DB is the single access path for documents + jobs; the session
    is opened here and closed by the caller. 503 when DATABASE_URL
    is unset — the PostgREST-only degraded mode is retired."""
    session = get_session()
    if session is None:
        raise ApiError(
            status_code=503,
            code="database_unavailable",
            message="The database is not configured on this server.",
        )
    try:
        yield (
            SqlAlchemyDocumentRepository(session),
            SqlAlchemyJobRepository(session),
        )
    finally:
        session.close()


@router.post(
    "/documents/register",
    response_model=RegisterResponse,
    status_code=201,
)
async def register_document(
    request: Request,
    payload: DocumentRegisterRequest,
    user: dict = Depends(get_current_user),
) -> RegisterResponse:
    rate_limiter.check(
        f"register:{user['id']}",
        settings.rate_limit_register_per_minute,
        settings.rate_limit_window_seconds,
    )
    with _repositories() as (documents, jobs):
        document, job, replay = job_service.register_document(user, payload, documents, jobs)
    response = RegisterResponse(
        document=DocumentResponse(**document),
        job=JobResponse(**job),
        idempotent_replay=replay,
    )
    # Idempotent replay answers 200 (nothing new was created); a fresh
    # registration answers 201.
    return JSONResponse(status_code=200 if replay else 201, content=response.model_dump())


@router.post("/documents/upload", response_model=UploadResponse)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    # M14 (ADR-010): optional query ?multi_pass=true — the worker
    # then runs the three-variant union OCR instead of the single
    # path. Default false: the single path, unchanged.
    multi_pass: bool = False,
    user: dict = Depends(get_current_user),
) -> UploadResponse:
    rate_limiter.check(
        f"register:{user['id']}",
        settings.rate_limit_register_per_minute,
        settings.rate_limit_window_seconds,
    )
    data = await file.read()
    recorder = _stage_recorder()
    try:
        with _repositories() as (documents, jobs):
            outcome = ingest_file(
                user=user,
                filename=file.filename or "upload",
                data=data,
                settings=settings,
                storage=_storage_backend(),
                documents=documents,
                jobs=jobs,
                recorder=recorder,
                correlation_id=getattr(request.state, "request_id", None),
                multi_pass=multi_pass,
            )
    finally:
        _close_recorder(recorder)
    if outcome.status == "rejected":
        codes = ", ".join(i.code for i in outcome.report.errors) or "invalid_file"
        raise ApiError(
            status_code=422,
            code=outcome.report.errors[0].code if outcome.report.errors else "invalid_file",
            message=f"File rejected: {codes}.",
        )
    return _upload_response(outcome)


@router.post("/documents/upload/batch", response_model=BatchUploadResponse)
async def upload_batch(
    request: Request,
    files: list[UploadFile] = File(...),
    # M14 (ADR-010): one ?multi_pass=true applies to the whole
    # batch — every file's job runs the union OCR. Default false.
    multi_pass: bool = False,
    user: dict = Depends(get_current_user),
) -> BatchUploadResponse:
    if len(files) > BATCH_MAX_FILES:
        raise ApiError(
            status_code=422,
            code="batch_too_large",
            message=f"Batch has {len(files)} files; limit is {BATCH_MAX_FILES}.",
        )
    rate_limiter.check(
        f"register:{user['id']}",
        settings.rate_limit_register_per_minute,
        settings.rate_limit_window_seconds,
    )
    recorder = _stage_recorder()
    try:
        with _repositories() as (documents, jobs):
            payloads: list[tuple[str, bytes]] = []
            for upload in files:
                payloads.append((upload.filename or "upload", await upload.read()))
            outcomes = ingest_batch(
                user=user,
                files=payloads,
                settings=settings,
                storage=_storage_backend(),
                documents=documents,
                jobs=jobs,
                recorder=recorder,
                correlation_id=getattr(request.state, "request_id", None),
                multi_pass=multi_pass,
            )
    finally:
        _close_recorder(recorder)
    results = [_upload_response(o) for o in outcomes]
    return BatchUploadResponse(
        results=results,
        stored=sum(1 for r in results if r.status == "stored"),
        replayed=sum(1 for r in results if r.status == "replay"),
        rejected=sum(1 for r in results if r.status == "rejected"),
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    request: Request,
    job_id: str,
    user: dict = Depends(get_current_user),
) -> JobResponse:
    with _repositories() as (_, jobs):
        job = job_service.get_job(user, job_id, jobs)
    return JobResponse(**job)


@router.post("/jobs/{job_id}/retry", response_model=JobResponse)
async def retry_job(
    request: Request,
    job_id: str,
    user: dict = Depends(get_current_user),
) -> JobResponse:
    rate_limiter.check(
        f"retry:{user['id']}",
        settings.rate_limit_retry_per_minute,
        settings.rate_limit_window_seconds,
    )
    with _repositories() as (_, jobs):
        job = job_service.retry_job(user, job_id, jobs)
    return JobResponse(**job)
