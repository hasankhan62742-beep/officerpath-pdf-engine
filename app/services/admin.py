# OfficerPath AI — Phase 2, M9
# Admin foundation (GAP-10, doc 05 §4). Read-only admin views
# over the engine DB — real rows only, never demo numbers. Every
# route is behind ``require_admin`` (app_metadata.is_admin from
# the verified JWT); the service layer itself never checks roles,
# the dependency is the enforcement point.
"""Admin service: overview counts, users, documents, jobs,
processing errors, and the question bank. All lists are
paginated and newest-first unless a filter says otherwise."""

import uuid
from collections import Counter
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models as db


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def overview(session: Session) -> dict:
    """Real counts for the admin dashboard. No invented numbers:
    every figure is a COUNT(*) over an engine table. NOTE the
    split, found by the M9 E2E cross-check: ``documents``/``jobs``
    are AUDIT totals (soft-deleted rows included — the admin
    documents list shows them with their ``deleted_at``), while
    ``questions`` is the LIVE bank (questions of soft-deleted
    documents excluded, exactly as the student bank list counts
    them — otherwise the overview and the bank disagree)."""
    jobs_by_status = dict(
        session.query(db.Job.status, func.count(db.Job.id)).group_by(db.Job.status).all()
    )
    live_questions = (
        session.query(func.count(db.ExtractedQuestion.id))
        .join(db.Document, db.ExtractedQuestion.document_id == db.Document.id)
        .filter(db.Document.deleted_at.is_(None))
        .scalar()
        or 0
    )
    return {
        "users": session.query(func.count(db.StudentProfile.id)).scalar() or 0,
        "documents": session.query(func.count(db.Document.id)).scalar() or 0,
        "jobs": session.query(func.count(db.Job.id)).scalar() or 0,
        "jobs_by_status": jobs_by_status,
        "questions": live_questions,
        "tests": session.query(func.count(db.TestSession.id)).scalar() or 0,
        "results": session.query(func.count(db.TestResult.id)).scalar() or 0,
        "errors": session.query(func.count(db.ProcessingError.id)).scalar() or 0,
        "notifications": session.query(func.count(db.Notification.id)).scalar() or 0,
    }


def list_users(session: Session, *, limit: int = 20, offset: int = 0) -> dict:
    """Student profiles + per-user real counts. NOTE: the engine
    DB stores NO student email (StudentProfile has no email
    column; /me returns the email from the caller's own JWT).
    The admin list therefore shows no email — the engine cannot
    invent one, and calling Auth admin APIs is out of M9 scope.
    A future step could add service-role auth.admin.list_users
    (needs the E2E stub + unit fake extended first)."""
    query = session.query(db.StudentProfile).order_by(db.StudentProfile.created_at.desc())
    total = query.count()
    profiles = query.limit(limit).offset(offset).all()
    user_ids = [p.user_id for p in profiles]
    doc_counts: Counter = Counter()
    test_counts: Counter = Counter()
    if user_ids:
        for user_id, count in (
            session.query(db.Document.user_id, func.count(db.Document.id))
            .filter(db.Document.user_id.in_(user_ids))
            .group_by(db.Document.user_id)
            .all()
        ):
            doc_counts[user_id] = count
        for user_id, count in (
            session.query(db.TestSession.user_id, func.count(db.TestSession.id))
            .filter(db.TestSession.user_id.in_(user_ids))
            .group_by(db.TestSession.user_id)
            .all()
        ):
            test_counts[user_id] = count
    return {
        "items": [
            {
                "user_id": str(p.user_id),
                "full_name": p.full_name,
                "phone": p.phone,
                "preferred_exam": p.preferred_exam,
                "education_level": p.education_level,
                "documents": doc_counts.get(p.user_id, 0),
                "tests": test_counts.get(p.user_id, 0),
                "created_at": _iso(p.created_at),
                "updated_at": _iso(p.updated_at),
            }
            for p in profiles
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def list_documents(
    session: Session, *, user_id: str | None = None, limit: int = 20, offset: int = 0
) -> dict:
    query = session.query(db.Document).order_by(db.Document.created_at.desc())
    if user_id is not None:
        query = query.filter(db.Document.user_id == uuid.UUID(user_id))
    total = query.count()
    rows = query.limit(limit).offset(offset).all()
    doc_ids = [r.id for r in rows]
    job_status: dict = {}
    if doc_ids:
        for doc_id, status in (
            session.query(db.Job.document_id, db.Job.status)
            .filter(db.Job.document_id.in_(doc_ids))
            .order_by(db.Job.created_at.desc())
            .all()
        ):
            job_status.setdefault(doc_id, status)
    return {
        "items": [
            {
                "id": str(r.id),
                "user_id": str(r.user_id),
                "title": r.title,
                "file_type": r.file_type,
                "file_size_bytes": r.file_size_bytes,
                "page_count": r.page_count,
                "latest_job_status": job_status.get(r.id),
                "is_shared": bool(r.is_shared),
                "deleted_at": _iso(r.deleted_at),
                "created_at": _iso(r.created_at),
            }
            for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def set_document_sharing(session: Session, *, document_id: str, is_shared: bool) -> dict:
    """Mark a document shared / unshared (M11). Admin-only —
    the route is behind ``require_admin``. Sharing makes the
    document's questions visible to every authenticated student
    in the test pool (read-only); unsharing removes them from
    the pool at once. A soft-deleted or unknown document
    answers 404 (never leaks existence)."""
    row = (
        session.query(db.Document)
        .filter(db.Document.id == uuid.UUID(document_id))
        .filter(db.Document.deleted_at.is_(None))
        .first()
    )
    if row is None:
        raise ApiError(status_code=404, code="not_found", message="Document not found.")
    row.is_shared = bool(is_shared)
    session.commit()
    return {
        "id": str(row.id),
        "user_id": str(row.user_id),
        "title": row.title,
        "is_shared": bool(row.is_shared),
    }


def list_jobs(
    session: Session, *, status: str | None = None, limit: int = 20, offset: int = 0
) -> dict:
    """Jobs with their error surface: the job's own error text
    plus how many processing_errors rows belong to the job, so
    the admin sees failures without opening a second table."""
    query = session.query(db.Job).order_by(db.Job.created_at.desc())
    if status is not None:
        query = query.filter(db.Job.status == status)
    total = query.count()
    rows = query.limit(limit).offset(offset).all()
    job_ids = [r.id for r in rows]
    error_counts: Counter = Counter()
    doc_titles: dict = {}
    if job_ids:
        for job_id, count in (
            session.query(db.ProcessingError.job_id, func.count(db.ProcessingError.id))
            .filter(db.ProcessingError.job_id.in_(job_ids))
            .group_by(db.ProcessingError.job_id)
            .all()
        ):
            error_counts[job_id] = count
        doc_ids = {r.document_id for r in rows}
        for doc_id, title in (
            session.query(db.Document.id, db.Document.title)
            .filter(db.Document.id.in_(doc_ids))
            .all()
        ):
            doc_titles[doc_id] = title
    return {
        "items": [
            {
                "id": str(r.id),
                "user_id": str(r.user_id),
                "document_id": str(r.document_id),
                "document_title": doc_titles.get(r.document_id),
                "status": r.status,
                "retry_count": r.retry_count,
                "error": r.error,
                "error_rows": error_counts.get(r.id, 0),
                "result_summary": r.result_summary,
                "created_at": _iso(r.created_at),
                "started_at": _iso(r.started_at),
                "completed_at": _iso(r.completed_at),
            }
            for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def list_errors(session: Session, *, limit: int = 20, offset: int = 0) -> dict:
    """Processing errors, newest first — the admin-visible error
    monitor. Rows are written by the pipeline/worker, never by
    hand; the admin view only reads them."""
    query = session.query(db.ProcessingError).order_by(db.ProcessingError.created_at.desc())
    total = query.count()
    rows = query.limit(limit).offset(offset).all()
    doc_ids = {r.document_id for r in rows}
    doc_titles: dict = {}
    if doc_ids:
        for doc_id, title in (
            session.query(db.Document.id, db.Document.title)
            .filter(db.Document.id.in_(doc_ids))
            .all()
        ):
            doc_titles[doc_id] = title
    return {
        "items": [
            {
                "id": str(r.id),
                "document_id": str(r.document_id),
                "document_title": doc_titles.get(r.document_id),
                "job_id": str(r.job_id) if r.job_id else None,
                "page_number": r.page_number,
                "stage": r.stage,
                "error_code": r.error_code,
                "message": r.message,
                "created_at": _iso(r.created_at),
            }
            for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _correct_index_from_label(label: str | None) -> int:
    if label and len(label) == 1 and "A" <= label <= "Z":
        return ord(label) - 65
    return -1


def list_questions(
    session: Session,
    *,
    validation_status: str | None = None,
    document_id: str | None = None,
    search: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Bank rows for admin question review. ``correct_index``
    comes from the latest resolved answer label (same rule as
    the student bank); -1 means unknown. Search matches the
    normalized question text (substring, case-insensitive).
    LIVE bank only: questions of soft-deleted documents are
    excluded, exactly as the student bank list excludes them
    (M9 E2E cross-check caught the overview/bank disagreement
    otherwise). The deleted document itself stays visible in
    the admin documents list (audit view)."""
    query = (
        session.query(db.ExtractedQuestion)
        .join(db.Document, db.ExtractedQuestion.document_id == db.Document.id)
        .filter(db.Document.deleted_at.is_(None))
        .order_by(db.ExtractedQuestion.created_at.desc())
    )
    if validation_status is not None:
        query = query.filter(db.ExtractedQuestion.validation_status == validation_status)
    if document_id is not None:
        query = query.filter(db.ExtractedQuestion.document_id == uuid.UUID(document_id))
    if search:
        query = query.filter(db.ExtractedQuestion.normalized_text.ilike(f"%{search}%"))
    total = query.count()
    rows = query.limit(limit).offset(offset).all()
    question_ids = [r.id for r in rows]
    option_counts: Counter = Counter()
    latest_answers: dict = {}
    if question_ids:
        for question_id, count in (
            session.query(db.QuestionOption.question_id, func.count(db.QuestionOption.id))
            .filter(db.QuestionOption.question_id.in_(question_ids))
            .group_by(db.QuestionOption.question_id)
            .all()
        ):
            option_counts[question_id] = count
        for answer in (
            session.query(db.ExtractedAnswer)
            .filter(db.ExtractedAnswer.question_id.in_(question_ids))
            .order_by(db.ExtractedAnswer.created_at.desc())
            .all()
        ):
            latest_answers.setdefault(answer.question_id, answer)
    return {
        "items": [
            {
                "id": str(r.id),
                "document_id": str(r.document_id),
                "question_number": r.question_number,
                "text": r.normalized_text,
                "options_count": option_counts.get(r.id, 0),
                "correct_index": _correct_index_from_label(
                    latest_answers[r.id].resolved_label if r.id in latest_answers else None
                ),
                "answer_status": latest_answers[r.id].status if r.id in latest_answers else None,
                "validation_status": r.validation_status,
                "extraction_method": r.extraction_method,
                "created_at": _iso(r.created_at),
            }
            for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
