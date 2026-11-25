# OfficerPath AI — PDF Engine (Phase 1, M6)
# Review API: synchronous document parse, review list, manual
# corrections, stored report.
#
# POST /documents/parse parses one PDF, TXT, or DOCX end to end
# in-process (digital text first, else per-page Tesseract OCR for
# PDFs; TXT/DOCX take the plain-text path, never PyMuPDF — A2) and
# returns the resolved MCQs + report. When DATABASE_URL is
# configured it also persists the Document + Job rows and the
# matched result, so the review endpoints below can find the
# items; without a database it still returns the parse result with
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
from app.pipeline.matching.service import IMAGE_MAGIC, parse_document_bytes, parse_image_bytes
from app.pipeline.matching.store import (
    apply_manual_correction,
    get_document_report,
    list_review_items,
    persist_matched_document,
)
from app.pipeline.matching.text import parse_text_bytes
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
from app.utils import metrics

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
    debug: dict | None = None,
    file_type: str = "pdf",
) -> uuid.UUID:
    """Create Document + Job rows (done — ADR-011) and persist the
    matched result under ``document_id``. Returns the job id.
    Also records the A3 page inventory when ``debug`` is given
    (the sync path never recorded DocumentPage rows at ingest,
    so the inventory upserts them)."""
    document = db.Document(
        id=document_id,
        user_id=user_id,
        title=filename,
        storage_path="inline-parse",
        file_type=file_type,
        file_size_bytes=len(data),
        page_count=page_count,
        content_hash=hashlib.sha256(data).hexdigest(),
    )
    session.add(document)
    session.flush()
    job = db.Job(
        user_id=user_id,
        document_id=document.id,
        status="done",  # ADR-011: the live 015 constraint rejects "completed".
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
    if debug is not None:
        from app.services.pages import record_page_inventory

        record_page_inventory(
            session,
            document_id=document.id,
            job_id=job.id,
            matched=matched,
            debug=debug,
        )
    return job.id


@router.post("/documents/parse", response_model=ParseResponse)
def parse_document(
    file: UploadFile = File(...),
    multi_pass: bool = False,
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
    if len(data) > settings.max_file_size_bytes:
        raise ApiError(
            status_code=422,
            code="file_too_large",
            message=f"File is {len(data)} bytes; limit is {settings.max_file_size_bytes}.",
        )
    # A2 (gap-report F4): the sync endpoint used to accept PDF only.
    # TXT/DOCX take the text path — never PyMuPDF. The kind is
    # decided by magic for PDF (unforgeable) and by extension for
    # txt/docx (plain text has no magic bytes); a mislabelled file
    # parses to zero questions or a named ValueError, never a crash.
    filename = file.filename or "upload.pdf"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if data.startswith(PDF_MAGIC):
        kind = "pdf"
    elif ext in ("txt", "docx"):
        kind = ext
    else:
        raise ApiError(
            status_code=422,
            code="invalid_file",
            message="Upload must be a PDF, TXT, or DOCX file.",
        )
    document_id = uuid.uuid4()
    try:
        if kind == "pdf":
            matched, report, debug = parse_document_bytes(
                data, str(document_id), multi_pass=multi_pass
            )
        else:
            matched, report, debug = parse_text_bytes(data, str(document_id), file_type=kind)
    except ValueError as exc:
        raise ApiError(status_code=422, code="invalid_file", message=str(exc)) from exc
    # M7 metrics: one documents_parsed sample + one OCR-call sample
    # per parsed page (digital = 1 "digital" call for the whole doc).
    engine = "digital" if debug["is_digital"] else "tesseract"
    metrics.inc("documents_parsed_total", {"engine": engine})
    metrics.inc(
        "ocr_calls_total",
        {"engine": engine},
        amount=debug["page_count"] if not debug["is_digital"] else 1,
    )
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
                debug=debug,
                file_type=kind,
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


@router.post("/documents/parse-image", response_model=ParseResponse)
def parse_image(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> ParseResponse:
    """Parse one photo (JPEG/PNG) — the server side of the Flutter
    ``importImage`` path (M7). The image is one scanned page: same
    OCR -> layout -> extract -> answers -> matching pipeline as a
    scanned PDF page, same resolved-MCQ response shape. The photo
    itself is never stored, only the parsed MCQs (like the PDF
    path). A non-image upload answers 422; an oversize upload 422
    (code file_too_large, same as the M1 upload contract).
    """
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
    if not data.startswith(IMAGE_MAGIC):
        raise ApiError(
            status_code=422,
            code="invalid_file",
            message="Upload must be a JPEG or PNG image.",
        )
    file_type = "png" if data.startswith(b"\x89PNG") else "jpg"
    document_id = uuid.uuid4()
    try:
        matched, report, debug = parse_image_bytes(data, str(document_id))
    except ValueError as exc:
        raise ApiError(status_code=422, code="invalid_file", message=str(exc)) from exc
    metrics.inc("documents_parsed_total", {"engine": "tesseract"})
    metrics.inc("ocr_calls_total", {"engine": "tesseract"})
    job_id: uuid.UUID | None = None
    persisted = False
    session = get_session()
    if session is not None:
        try:
            job_id = _persist_parse(
                session,
                document_id=document_id,
                user_id=uuid.UUID(user["id"]),
                filename=file.filename or "upload.jpg",
                data=data,
                page_count=debug["page_count"],
                matched=matched,
                debug=debug,
                file_type=file_type,
            )
            persisted = True
        except Exception:
            session.rollback()
            matched.notes.append("persistence failed — result returned unpersisted")
        finally:
            session.close()
    return ParseResponse(
        document_id=str(document_id),
        job_id=str(job_id) if job_id is not None else None,
        persisted=persisted,
        filename=file.filename or "upload.jpg",
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
