# OfficerPath AI — Phase 2, M4
# Document listing / detail / dashboard summary / soft delete.
#
# Ownership: every function filters by the JWT's user id and
# answers 404 for unknown, deleted, or another user's documents —
# never leaks existence (the Phase 1 pattern). All numbers come
# from real engine-DB rows.

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.database.sqlalchemy_repositories import (
    JOB_STATUSES,
    SqlAlchemyDocumentRepository,
    SqlAlchemyJobRepository,
)
from app.db import models as db
from app.storage.base import StorageBackend
from app.utils.logging import get_logger

log = get_logger(__name__)

#: A document's list item carries its latest job; the job's
#: result_summary is the source of the question counts.
TERMINAL_STATUSES = ("done", "failed", "cancelled")


def _item(document: dict, job: dict | None) -> dict:
    summary = (job or {}).get("result_summary") or {}
    return {
        "id": document["id"],
        "title": document["title"],
        "file_type": document["file_type"],
        "file_size_bytes": document["file_size_bytes"],
        "page_count": document.get("page_count"),
        "created_at": document["created_at"],
        "job": job,
        "is_shared": bool(document.get("is_shared", False)),
        "questions": summary.get("questions")
        if isinstance(summary.get("questions"), int)
        else None,
        "answered": summary.get("answered") if isinstance(summary.get("answered"), int) else None,
    }


def _own_document(
    user: dict,
    document_id: str,
    documents: SqlAlchemyDocumentRepository,
) -> dict:
    """The caller's own, not-deleted document — 404 otherwise."""
    row = documents.find_by_id(document_id)
    if row is None or row.get("user_id") != user["id"]:
        raise ApiError(status_code=404, code="not_found", message="Document not found.")
    if row.get("deleted_at") is not None:
        raise ApiError(status_code=404, code="not_found", message="Document not found.")
    return row


def list_documents(
    user: dict,
    documents: SqlAlchemyDocumentRepository,
    jobs: SqlAlchemyJobRepository,
    *,
    limit: int,
    offset: int,
    status: str | None = None,
    include_shared: bool = False,
) -> tuple[list[dict], int]:
    """(page of items, total). `status` filters by the document's
    latest job status; a document with no job never matches a
    status filter. Total counts the filtered set, not the page.
    ``include_shared`` (M11, test builder only) also lists
    shared bank documents, flagged by ``is_shared``."""
    if status is not None and status not in JOB_STATUSES:
        raise ApiError(
            status_code=422,
            code="validation_error",
            message=f"Unknown job status: {status!r}.",
        )
    rows, total = documents.list_by_user(
        user["id"], limit=limit, offset=offset, status=status, include_shared=include_shared
    )
    job_map = jobs.find_latest_by_document_ids([r["id"] for r in rows])
    return [_item(row, job_map.get(row["id"])) for row in rows], total


def get_document_detail(
    user: dict,
    document_id: str,
    documents: SqlAlchemyDocumentRepository,
    jobs: SqlAlchemyJobRepository,
    session: Session,
) -> dict:
    """Document + its latest job + the job's stage history."""
    row = _own_document(user, document_id, documents)
    job = jobs.find_by_document_id(row["id"])
    stages: list[dict] = []
    if job is not None:
        stage_rows = (
            session.query(db.ProcessingStage)
            .filter(db.ProcessingStage.job_id == uuid.UUID(job["id"]))
            .order_by(db.ProcessingStage.created_at)
            .all()
        )
        stages = [
            {
                "stage": s.stage,
                "status": s.status,
                "detail": s.detail,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in stage_rows
        ]
    return {
        "document": row,
        "job": job,
        "stages": stages,
    }


def get_dashboard_summary(
    user: dict,
    documents: SqlAlchemyDocumentRepository,
    jobs: SqlAlchemyJobRepository,
    *,
    recent_limit: int = 5,
) -> dict:
    """Real dashboard numbers: document total, job counts by
    status (all six vocabulary values, zeros included), and the
    newest documents with their jobs."""
    rows, total = documents.list_by_user(user["id"], limit=recent_limit, offset=0)
    job_map = jobs.find_latest_by_document_ids([r["id"] for r in rows])
    return {
        "documents_total": total,
        "jobs_by_status": jobs.count_by_status_for_user(user["id"]),
        "recent_documents": [_item(r, job_map.get(r["id"])) for r in rows],
    }


def delete_document(
    user: dict,
    document_id: str,
    documents: SqlAlchemyDocumentRepository,
    jobs: SqlAlchemyJobRepository,
    session: Session,
    storage: StorageBackend,
) -> dict:
    """Soft-delete the caller's own document. A queued/processing
    job is cancelled first (same rules as the cancel endpoint);
    a terminal job is left as-is. Stored bytes on local disk are
    removed best-effort — a missing file is not an error, and
    bucket-registered bytes are never touched from here (the
    bucket is owned by Supabase storage, not this endpoint)."""
    from app.workers.processor import cancel_job as processor_cancel_job

    row = _own_document(user, document_id, documents)
    job = jobs.find_by_document_id(row["id"])
    job_cancelled = False
    if job is not None and job.get("status") not in TERMINAL_STATUSES:
        try:
            processor_cancel_job(session, job_id=uuid.UUID(job["id"]), user_id=user["id"])
            job_cancelled = True
        except ApiError as exc:
            # A job that cannot be cancelled (e.g. raced to a
            # terminal state) must not block the delete.
            log.info(
                "document delete: job cancel skipped",
                extra={"fields": {"job_id": job["id"], "code": exc.code}},
            )
    deleted = documents.soft_delete(row["id"], user["id"])
    if deleted is None:
        raise ApiError(status_code=404, code="not_found", message="Document not found.")
    storage_path = row.get("storage_path") or ""
    if storage_path and storage_path != "inline-parse":
        try:
            storage.delete(storage_path)
        except Exception:  # noqa: BLE001 — best-effort cleanup only
            log.info(
                "document delete: stored bytes cleanup skipped",
                extra={"fields": {"document_id": row["id"]}},
            )
    log.info(
        "Document soft-deleted",
        extra={
            "fields": {
                "user_id": user["id"],
                "document_id": row["id"],
                "job_cancelled": job_cancelled,
            }
        },
    )
    return {"document_id": row["id"], "deleted": True, "job_cancelled": job_cancelled}
