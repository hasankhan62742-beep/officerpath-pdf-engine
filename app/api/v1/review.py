# OfficerPath AI — PDF Engine (Phase 1, M6)
# Review API: synchronous document parse, review list, manual
# corrections, stored report.
#
# POST /documents/parse parses one PDF end to end in-process
# (digital text first, else per-page Tesseract OCR) and returns
# the resolved MCQs + report. When DATABASE_URL is configured it
# also persists the Document + Job rows and the matched result, so
# the review endpoints below can find the items; without a
# database it still returns the parse result with
# ``persisted: false`` (a good parse never fails on bookkeeping).
#
# Manual corrections are the top of the answer-precedence chain
# (manual > key > inline > style > visual > inferred). A
# correction never edits the original extraction (original_*
# untouched); it writes the normalized field, records old/new in
# manual_corrections, appends a review_history row, and re-runs
# validation. If the server is unreachable the Flutter toggle
# path must surface the error — it must NEVER silently fall back
# to a different parser.

import hashlib
import uuid

from fastapi import APIRouter, Depends, File, UploadFile

from app.config import settings
from app.core.errors import ApiError
from app.db import models as db
from app.db.session import get_session
from app.pipeline.matching.service import parse_document_bytes
from app.pipeline.matching.store import (
    apply_manual_correction,
    get_document_report,
    list_review_items,
    persist_matched_document,
)
from app.schemas.review import (
    CorrectionRequest,
    CorrectionResponse,
    DocumentReportResponse,
    ParseResponse,
    ReviewItemResponse,
    ReviewListResponse,
)
from app.security.dependencies import get_current_user
from app.security.rate_limit import rate_limiter

router = APIRouter(prefix="/api/v1", tags=["review"])

#: Parse rejects non-PDF bytes before any work.
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


def _require_job_for_user(session, job_id: str, user_id: str) -> db.Job:
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise ApiError(status_code=404, code="not_found", message="Job not found.") from None
    job = session.query(db.Job).filter(db.Job.id == job_uuid).first()
    if job is None or str(job.user_id) != user_id:
        raise ApiError(status_code=404, code="not_found", message="Job not found.")
    return job


def _require_document_for_user(session, document_id: str, user_id: str) -> db.Document:
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise ApiError(status_code=404, code="not_found", message="Document not found.") from None
    document = session.query(db.Document).filter(db.Document.id == doc_uuid).first()
    if document is None or str(document.user_id) != user_id:
        raise ApiError(status_code=404, code="not_found", message="Document not found.")
    return document


def _persist_parse(
    session,
    *,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
    filename: str,
    data: bytes,
    page_count: int,
    matched,
) -> uuid.UUID:
    """Create Document + Job rows (completed) and persist the
    matched result under ``document_id``. Returns the job id."""
    document = db.Document(
        id=document_id,
        user_id=user_id,
        title=filename,
        storage_path="inline-parse",
        file_type="pdf",
        file_size_bytes=len(data),
        page_count=page_count,
        content_hash=hashlib.sha256(data).hexdigest(),
    )
    session.add(document)
    session.flush()
    job = db.Job(
        user_id=user_id,
        document_id=document.id,
        status="completed",
        idempotency_key=None,
    )
    session.add(job)
    session.flush()
    persist_matched_document(
        session,
        document_id=document.id,
        job_id=job.id,
        matched=matched,
    )
    return job.id


@router.post("/documents/parse", response_model=ParseResponse)
def parse_document(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> ParseResponse:
    # Plain `def` (not async): FastAPI runs it in a threadpool, so
    # the CPU-heavy OCR never blocks the event loop. The upload is
    # read synchronously from the underlying file object.
    rate_limiter.check(
        f"parse:{user['id']}",
        settings.rate_limit_register_per_minute,
        settings.rate_limit_window_seconds,
    )
    data = file.file.read()
    if not data.startswith(PDF_MAGIC):
        raise ApiError(
            status_code=422,
            code="invalid_file",
            message="Upload must be a PDF file.",
        )
    document_id = uuid.uuid4()
    try:
        matched, report, debug = parse_document_bytes(data, str(document_id))
    except ValueError as exc:
        raise ApiError(status_code=422, code="invalid_file", message=str(exc)) from exc
    job_id: uuid.UUID | None = None
    persisted = False
    session = get_session()
    if session is not None:
        try:
            job_id = _persist_parse(
                session,
                document_id=document_id,
                user_id=uuid.UUID(user["id"]),
                filename=file.filename or "upload.pdf",
                data=data,
                page_count=debug["page_count"],
                matched=matched,
            )
            persisted = True
        except Exception:
            # Bookkeeping failure never fails a good parse.
            session.rollback()
            matched.notes.append("persistence failed — result returned unpersisted")
        finally:
            session.close()
    return ParseResponse(
        document_id=str(document_id),
        job_id=str(job_id) if job_id is not None else None,
        persisted=persisted,
        filename=file.filename or "upload.pdf",
        is_digital=debug["is_digital"],
        page_count=debug["page_count"],
        matched=matched.to_dict(),
        report=report,
        debug=debug,
    )


@router.get("/jobs/{job_id}/review", response_model=ReviewListResponse)
def get_review_list(
    job_id: str,
    user: dict = Depends(get_current_user),
) -> ReviewListResponse:
    session = _session_or_503()
    try:
        job = _require_job_for_user(session, job_id, user["id"])
        items = list_review_items(session, job_id=job.id)
    finally:
        session.close()
    return ReviewListResponse(
        job_id=str(job.id),
        items=[ReviewItemResponse(**item) for item in items],
        count=len(items),
    )


@router.post(
    "/documents/{document_id}/questions/{question_id}/corrections",
    response_model=CorrectionResponse,
)
def post_correction(
    document_id: str,
    question_id: str,
    payload: CorrectionRequest,
    user: dict = Depends(get_current_user),
) -> CorrectionResponse:
    rate_limiter.check(
        f"correct:{user['id']}",
        settings.rate_limit_retry_per_minute,
        settings.rate_limit_window_seconds,
    )
    session = _session_or_503()
    try:
        document = _require_document_for_user(session, document_id, user["id"])
        try:
            question_uuid = uuid.UUID(question_id)
        except ValueError:
            raise ApiError(
                status_code=404, code="not_found", message="Question not found."
            ) from None
        try:
            result = apply_manual_correction(
                session,
                document_id=document.id,
                user_id=uuid.UUID(user["id"]),
                question_id=question_uuid,
                field=payload.field,
                new_value=payload.new_value,
                reason=payload.reason,
            )
        except ValueError as exc:
            raise ApiError(status_code=422, code="invalid_correction", message=str(exc)) from exc
    finally:
        session.close()
    return CorrectionResponse(**result)


@router.get("/documents/{document_id}/report", response_model=DocumentReportResponse)
def get_report(
    document_id: str,
    user: dict = Depends(get_current_user),
) -> DocumentReportResponse:
    session = _session_or_503()
    try:
        document = _require_document_for_user(session, document_id, user["id"])
        report = get_document_report(session, document_id=document.id)
    finally:
        session.close()
    if report is None:
        raise ApiError(
            status_code=404,
            code="not_found",
            message="No report stored for this document.",
        )
    return DocumentReportResponse(**report)
