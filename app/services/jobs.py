# OfficerPath AI — PDF Engine (Phase 1A)
# Job/document service: the business rules for register / status / retry.
#
# Ownership: a user may only register documents under their own user id
# and their own storage folder (`<user_id>/...`), and may only read or
# retry their own jobs. Other users' jobs are answered with 404 (never
# leak existence).
#
# Idempotency: a repeated register with the same idempotency key (same
# user) — or the same storage path for the same user — returns the
# ORIGINAL document + job instead of creating duplicates.

from app.core.errors import ApiError
from app.database.sqlalchemy_repositories import (
    RETRYABLE_STATUSES,
    SqlAlchemyDocumentRepository,
    SqlAlchemyJobRepository,
)
from app.schemas.documents import DocumentRegisterRequest
from app.utils.logging import get_logger

log = get_logger(__name__)


def _owns_storage_path(user_id: str, storage_path: str) -> bool:
    return storage_path == user_id or storage_path.startswith(user_id + "/")


def register_document(
    user: dict,
    payload: DocumentRegisterRequest,
    documents: SqlAlchemyDocumentRepository,
    jobs: SqlAlchemyJobRepository,
    *,
    source: str = "register",
    multi_pass: bool = False,
) -> tuple[dict, dict, bool]:
    """Register a document + job. `source` records where the bytes
    live (ADR-011): "register" = client-uploaded to the Supabase
    bucket (the worker must NOT claim it — no local bytes — until
    M4 wires bucket download); "upload" = bytes on local disk (the
    worker may claim it). Stored in the job's result_summary so the
    worker's claim filter can read it without a schema change.
    `multi_pass` (M14, ADR-010) records that the worker must run
    the three-variant union OCR instead of the single path; it is
    stored only when True, so the default job row is unchanged."""
    user_id = user["id"]

    # Ownership: the storage path must live under the caller's own folder.
    if not _owns_storage_path(user_id, payload.storage_path):
        raise ApiError(
            status_code=403,
            code="forbidden",
            message="Documents must be registered under your own storage folder.",
        )

    # Idempotency key replay (same user + same key -> same job).
    if payload.idempotency_key:
        existing_job = jobs.find_by_user_and_idempotency_key(user_id, payload.idempotency_key)
        if existing_job is not None:
            existing_doc = documents.find_by_user_and_path(user_id, payload.storage_path)
            # The job exists, so its document must exist too; if it does
            # not (partial write), treat as a server error, not a new job.
            if existing_doc is None:
                raise ApiError(
                    status_code=500,
                    code="internal_error",
                    message="An unexpected error occurred.",
                )
            log.info(
                "Idempotent replay of document register",
                extra={"fields": {"user_id": user_id, "job_id": existing_job["id"]}},
            )
            return existing_doc, existing_job, True

    # Same storage path + same user -> same job (no duplicates).
    existing_doc = documents.find_by_user_and_path(user_id, payload.storage_path)
    if existing_doc is not None:
        existing_job = jobs.find_by_document_id(existing_doc["id"])
        if existing_job is not None:
            log.info(
                "Duplicate register for existing storage path; returning original job",
                extra={"fields": {"user_id": user_id, "job_id": existing_job["id"]}},
            )
            return existing_doc, existing_job, True

    document = documents.create(
        {
            "user_id": user_id,
            "title": payload.title,
            "storage_path": payload.storage_path,
            "file_type": payload.file_type.value,
            "file_size_bytes": payload.file_size_bytes,
            "page_count": payload.page_count,
            "content_hash": payload.content_hash,
            "metadata": payload.metadata,
        }
    )
    job = jobs.create(
        {
            "user_id": user_id,
            "document_id": document["id"],
            "status": "queued",
            "idempotency_key": payload.idempotency_key,
            # ADR-011: marks register-source jobs so the worker skips
            # them (bucket bytes, not local disk) until M4.
            # M14: "multi_pass" only when requested — the default
            # row stays {"source": source}.
            "result_summary": (
                {"source": source, "multi_pass": True} if multi_pass else {"source": source}
            ),
        }
    )
    log.info(
        "Document registered",
        extra={
            "fields": {
                "user_id": user_id,
                "document_id": document["id"],
                "job_id": job["id"],
            }
        },
    )
    return document, job, False


def get_job(user: dict, job_id: str, jobs: SqlAlchemyJobRepository) -> dict:
    job = jobs.find_by_id(job_id)
    if job is None or job.get("user_id") != user["id"]:
        # 404 for other users' jobs too — never leak existence.
        raise ApiError(status_code=404, code="not_found", message="Job not found.")
    return job


def retry_job(user: dict, job_id: str, jobs: SqlAlchemyJobRepository) -> dict:
    job = get_job(user, job_id, jobs)
    if job.get("status") not in RETRYABLE_STATUSES:
        raise ApiError(
            status_code=409,
            code="job_not_retryable",
            message=(
                "Only failed or cancelled jobs can be retried. "
                f"Current status: {job.get('status')}."
            ),
        )
    updated = jobs.update(
        job_id,
        {
            "status": "queued",
            "retry_count": int(job.get("retry_count") or 0) + 1,
            "started_at": None,
            "completed_at": None,
            "error": None,
        },
    )
    if updated is None:
        raise ApiError(
            status_code=500, code="internal_error", message="An unexpected error occurred."
        )
    log.info(
        "Job retried",
        extra={
            "fields": {
                "user_id": user["id"],
                "job_id": job_id,
                "retry_count": updated["retry_count"],
            }
        },
    )
    return updated
