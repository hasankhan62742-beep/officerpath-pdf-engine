# OfficerPath AI — PDF Engine (Phase 2, M3)
# SQLAlchemy repositories for `documents` and `jobs` (ADR-011).
#
# They implement the SAME dict-based interface the deleted
# PostgREST repositories (`app/database/repositories.py`) had, so
# `app/services/jobs.py` and `app/pipeline/ingestion/service.py`
# are unchanged in logic: find/create/update by plain dicts, ids
# and timestamps generated in Python, one commit per call (the
# PostgREST auto-commit parity — a document created without its
# job on a mid-request crash is possible, as before; a single
# transaction across both creates is M4 follow-up, not M3).
#
# Why SQLAlchemy, not PostgREST: the engine DB IS the Supabase
# Postgres database (DATABASE_URL points at it; the models mirror
# the 015 tables), so this is the same store through one access
# path — one vocabulary (`done`, ADR-011), one ownership model
# (code-level per-user 404s), one test backend. The PostgREST
# path is retired with the repositories module.
#
# The session is owned by the caller (routes open one per request
# and close it); the repositories never close it.

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import models as db

#: Job status vocabulary (ADR-011). Terminal status is `done` —
#: the live 015 check constraint rejects `completed`.
JOB_STATUSES = ("queued", "uploading", "processing", "done", "failed", "cancelled")
RETRYABLE_STATUSES = ("failed", "cancelled")


def _now() -> datetime:
    return datetime.now(UTC)


def _document_row(doc: db.Document) -> dict:
    return {
        "id": str(doc.id),
        "user_id": str(doc.user_id),
        "title": doc.title,
        "storage_path": doc.storage_path,
        "file_type": doc.file_type,
        "file_size_bytes": doc.file_size_bytes,
        "page_count": doc.page_count,
        "content_hash": doc.content_hash,
        "metadata": doc.metadata_json,
        "deleted_at": doc.deleted_at.isoformat() if doc.deleted_at else None,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


def _job_row(job: db.Job) -> dict:
    return {
        "id": str(job.id),
        "user_id": str(job.user_id),
        "document_id": str(job.document_id),
        "status": job.status,
        "retry_count": job.retry_count,
        "error": job.error,
        "result_summary": job.result_summary,
        "idempotency_key": job.idempotency_key,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def _as_uuid(value: str | UUID) -> UUID | None:
    """Coerce to UUID, or None for a malformed id (a bad id is a
    404, never a 500 — the old PostgREST repositories compared
    strings and simply found nothing)."""
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _require_uuid(value: str | UUID) -> UUID:
    """Strict coercion for creates: ids here come from the JWT or
    from rows this code just created, so a malformed value is a
    server bug, not a 404."""
    parsed = _as_uuid(value)
    if parsed is None:
        raise ValueError(f"malformed UUID: {value!r}")
    return parsed


class SqlAlchemyDocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, document_id: str) -> dict | None:
        doc_uuid = _as_uuid(document_id)
        if doc_uuid is None:
            return None
        row = self._session.get(db.Document, doc_uuid)
        return _document_row(row) if row is not None else None

    def find_by_user_and_path(self, user_id: str, storage_path: str) -> dict | None:
        user_uuid = _as_uuid(user_id)
        if user_uuid is None:
            return None
        row = (
            self._session.query(db.Document)
            .filter(
                db.Document.user_id == user_uuid,
                db.Document.storage_path == storage_path,
                # A soft-deleted document does not block re-registration
                # of the same path (M4): deleting then re-uploading the
                # same file creates a fresh document.
                db.Document.deleted_at.is_(None),
            )
            .first()
        )
        return _document_row(row) if row is not None else None

    def find_by_user_and_sha256(self, user_id: str, sha256: str) -> dict | None:
        """SHA-256 dedup lookup (per user only — never reveal another
        user's file). Soft-deleted rows do not dedup (M4)."""
        user_uuid = _as_uuid(user_id)
        if user_uuid is None:
            return None
        row = (
            self._session.query(db.Document)
            .filter(
                db.Document.user_id == user_uuid,
                db.Document.content_hash == sha256,
                db.Document.deleted_at.is_(None),
            )
            .first()
        )
        return _document_row(row) if row is not None else None

    def create(self, data: dict) -> dict:
        row = db.Document(
            id=uuid.uuid4(),
            user_id=_require_uuid(data["user_id"]),
            title=data["title"],
            storage_path=data["storage_path"],
            file_type=data["file_type"],
            file_size_bytes=data["file_size_bytes"],
            page_count=data.get("page_count"),
            content_hash=data.get("content_hash"),
            metadata_json=data.get("metadata"),
            created_at=_now(),
        )
        self._session.add(row)
        self._session.commit()
        return _document_row(row)

    def list_by_user(
        self, user_id: str, *, limit: int, offset: int, status: str | None = None
    ) -> tuple[list[dict], int]:
        """The user's documents, newest first, excluding soft-deleted
        rows. Returns (page, total) so the caller can paginate.
        `status` filters by the document's job status (one job per
        document — register/upload/async each create exactly one —
        so the join is 1:1 in practice)."""
        user_uuid = _as_uuid(user_id)
        if user_uuid is None:
            return [], 0
        base = self._session.query(db.Document).filter(
            db.Document.user_id == user_uuid,
            db.Document.deleted_at.is_(None),
        )
        if status is not None:
            base = base.join(db.Job, db.Job.document_id == db.Document.id).filter(
                db.Job.status == status
            )
        total = base.count()
        rows = base.order_by(db.Document.created_at.desc()).limit(limit).offset(offset).all()
        return [_document_row(r) for r in rows], total

    def soft_delete(self, document_id: str, user_id: str) -> dict | None:
        """Set `deleted_at` on the caller's own, not-yet-deleted
        document. Returns the row, or None (404 — unknown, another
        user's, or already deleted)."""
        doc_uuid = _as_uuid(document_id)
        user_uuid = _as_uuid(user_id)
        if doc_uuid is None or user_uuid is None:
            return None
        row = self._session.get(db.Document, doc_uuid)
        if row is None or row.user_id != user_uuid or row.deleted_at is not None:
            return None
        row.deleted_at = _now()
        self._session.commit()
        return _document_row(row)


class SqlAlchemyJobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, job_id: str) -> dict | None:
        job_uuid = _as_uuid(job_id)
        if job_uuid is None:
            return None
        row = self._session.get(db.Job, job_uuid)
        return _job_row(row) if row is not None else None

    def find_by_user_and_idempotency_key(self, user_id: str, idempotency_key: str) -> dict | None:
        user_uuid = _as_uuid(user_id)
        if user_uuid is None:
            return None
        row = (
            self._session.query(db.Job)
            .filter(
                db.Job.user_id == user_uuid,
                db.Job.idempotency_key == idempotency_key,
            )
            .first()
        )
        return _job_row(row) if row is not None else None

    def find_by_document_id(self, document_id: str) -> dict | None:
        doc_uuid = _as_uuid(document_id)
        if doc_uuid is None:
            return None
        row = self._session.query(db.Job).filter(db.Job.document_id == doc_uuid).first()
        return _job_row(row) if row is not None else None

    def find_latest_by_document_ids(self, document_ids: list[str]) -> dict[str, dict]:
        """Latest job per document (one row per document in practice;
        newest by created_at wins). Keys are document ids as strings."""
        uuids = [u for u in (_as_uuid(d) for d in document_ids) if u is not None]
        if not uuids:
            return {}
        rows = (
            self._session.query(db.Job)
            .filter(db.Job.document_id.in_(uuids))
            .order_by(db.Job.created_at.desc())
            .all()
        )
        out: dict[str, dict] = {}
        for row in rows:
            key = str(row.document_id)
            if key not in out:
                out[key] = _job_row(row)
        return out

    def count_by_status_for_user(self, user_id: str) -> dict[str, int]:
        """Job counts by status for the user's NOT-deleted documents.
        Every vocabulary value is present (zeros are real counts,
        not missing data)."""
        user_uuid = _as_uuid(user_id)
        counts = dict.fromkeys(JOB_STATUSES, 0)
        if user_uuid is None:
            return counts
        rows = (
            self._session.query(db.Job.status, func.count(db.Job.id))
            .join(db.Document, db.Job.document_id == db.Document.id)
            .filter(
                db.Document.user_id == user_uuid,
                db.Document.deleted_at.is_(None),
            )
            .group_by(db.Job.status)
            .all()
        )
        for status, n in rows:
            if status in counts:
                counts[status] = int(n)
        return counts

    def create(self, data: dict) -> dict:
        row = db.Job(
            id=uuid.uuid4(),
            user_id=_require_uuid(data["user_id"]),
            document_id=_require_uuid(data["document_id"]),
            status=data.get("status", "queued"),
            idempotency_key=data.get("idempotency_key"),
            retry_count=0,
            error=None,
            result_summary=data.get("result_summary"),
            created_at=_now(),
        )
        self._session.add(row)
        self._session.commit()
        return _job_row(row)

    def update(self, job_id: str, data: dict) -> dict | None:
        job_uuid = _as_uuid(job_id)
        if job_uuid is None:
            return None
        row = self._session.get(db.Job, job_uuid)
        if row is None:
            return None
        for key, value in data.items():
            if key == "status":
                row.status = value
            elif key == "retry_count":
                row.retry_count = value
            elif key == "started_at":
                row.started_at = value
            elif key == "completed_at":
                row.completed_at = value
            elif key == "error":
                row.error = value
            elif key == "result_summary":
                row.result_summary = value
            # Unknown keys are ignored (same as the PostgREST
            # repositories, which passed only known columns).
        self._session.commit()
        return _job_row(row)


__all__ = [
    "JOB_STATUSES",
    "RETRYABLE_STATUSES",
    "SqlAlchemyDocumentRepository",
    "SqlAlchemyJobRepository",
]
