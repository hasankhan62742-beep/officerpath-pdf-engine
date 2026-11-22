# OfficerPath AI — Phase 2, M5
# Question bank + results reads (GAP-3) and subjects (GAP-4).
#
# Ownership: every query joins the question's document and
# filters by the JWT's user id; soft-deleted documents never
# appear. Unknown/other-user questions answer 404 (never leaks
# existence — the Phase 1 pattern). All numbers come from real
# engine-DB rows; confidence is null when there is no answer
# row, never an invented number.
#
# This is a READ layer over the Phase 1 store — it never edits
# extracted rows, options, answers, or evidence. Corrections go
# through the existing M6 endpoint (review.py); this module only
# lists the audit trail.
#
# Sorting: document questions are ordered by their printed
# number (numeric when parseable), not by created_at — SQLite
# timestamps have second precision, so created_at ties would
# scramble the order (the same trap M4 hit on job FIFO order).

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import exists
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models as db
from app.utils.logging import get_logger

log = get_logger(__name__)

#: Filter values accepted by ``?status=`` on the bank list.
BANK_STATUSES = ("answered", "unknown", "pending", "inferred", "corrected", "conflicting")

_INFERRED = ("inferred", "inferred_formatting")


def _not_found(what: str = "Question not found.") -> ApiError:
    return ApiError(status_code=404, code="not_found", message=what)


def _parse_uuid(value: str, what: str = "Question not found.") -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise _not_found(what) from None


def _own_question(session: Session, user_id: str, question_id: uuid.UUID) -> db.ExtractedQuestion:
    """The caller's own question (via its document) — 404 otherwise."""
    row = (
        session.query(db.ExtractedQuestion)
        .join(db.Document, db.Document.id == db.ExtractedQuestion.document_id)
        .filter(db.ExtractedQuestion.id == question_id)
        .filter(db.Document.user_id == uuid.UUID(user_id))
        .filter(db.Document.deleted_at.is_(None))
        .first()
    )
    if row is None:
        raise _not_found()
    return row


def _own_document(session: Session, user_id: str, document_id: uuid.UUID) -> db.Document:
    row = (
        session.query(db.Document)
        .filter(db.Document.id == document_id)
        .filter(db.Document.user_id == uuid.UUID(user_id))
        .filter(db.Document.deleted_at.is_(None))
        .first()
    )
    if row is None:
        raise ApiError(status_code=404, code="not_found", message="Document not found.")
    return row


def _latest_answer(session: Session, question_id: uuid.UUID) -> db.ExtractedAnswer | None:
    return (
        session.query(db.ExtractedAnswer)
        .filter(db.ExtractedAnswer.question_id == question_id)
        .order_by(db.ExtractedAnswer.created_at.desc())
        .first()
    )


def _batch_answers(
    session: Session, question_ids: list[uuid.UUID]
) -> dict[uuid.UUID, db.ExtractedAnswer]:
    """Latest answer per question, one query (not N+1)."""
    if not question_ids:
        return {}
    rows = (
        session.query(db.ExtractedAnswer)
        .filter(db.ExtractedAnswer.question_id.in_(question_ids))
        .order_by(db.ExtractedAnswer.created_at.desc())
        .all()
    )
    out: dict[uuid.UUID, db.ExtractedAnswer] = {}
    for row in rows:
        out.setdefault(row.question_id, row)
    return out


def _batch_options(session: Session, question_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    if not question_ids:
        return {}
    rows = (
        session.query(db.QuestionOption)
        .filter(db.QuestionOption.question_id.in_(question_ids))
        .order_by(db.QuestionOption.position)
        .all()
    )
    out: dict[uuid.UUID, list[str]] = {qid: [] for qid in question_ids}
    for row in rows:
        out.setdefault(row.question_id, []).append(row.normalized_text)
    return out


def _batch_corrected(session: Session, question_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if not question_ids:
        return set()
    rows = (
        session.query(db.ManualCorrection.target_id)
        .filter(db.ManualCorrection.target_id.in_(question_ids))
        .distinct()
        .all()
    )
    return {r[0] for r in rows}


def _batch_subjects(session: Session, question_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict]]:
    if not question_ids:
        return {}
    rows = (
        session.query(db.QuestionSubject, db.Subject, db.Topic)
        .join(db.Subject, db.Subject.id == db.QuestionSubject.subject_id, isouter=True)
        .join(db.Topic, db.Topic.id == db.QuestionSubject.topic_id, isouter=True)
        .filter(db.QuestionSubject.question_id.in_(question_ids))
        .order_by(db.QuestionSubject.created_at)
        .all()
    )
    out: dict[uuid.UUID, list[dict]] = {qid: [] for qid in question_ids}
    for assignment, subject, topic in rows:
        out.setdefault(assignment.question_id, []).append(
            {
                "subject_id": str(assignment.subject_id) if assignment.subject_id else "",
                "subject_name": subject.name if subject else "",
                "subject_slug": subject.slug if subject else "",
                "topic_id": str(assignment.topic_id) if assignment.topic_id else None,
                "topic_name": topic.name if topic else None,
            }
        )
    return out


def _is_inferred(answer: db.ExtractedAnswer | None) -> bool:
    return bool(
        answer
        and ((answer.resolution_method or "") in _INFERRED or (answer.status or "") in _INFERRED)
    )


def _answer_status(validation_status: str, answer: db.ExtractedAnswer | None) -> str:
    """M5 display label: verified / detected / unknown /
    needs_review / conflicting."""
    if validation_status == "pending":
        return "needs_review"
    if answer is None or not answer.resolved_label:
        return "unknown"
    if (answer.status or "") == "conflicting":
        return "conflicting"
    if (answer.status or "") in ("verified_explicit_key", "manually_verified"):
        return "verified"
    return "detected"


def _correct_index(answer: db.ExtractedAnswer | None) -> int:
    if answer is None or not answer.resolved_label:
        return -1
    index = ord(answer.resolved_label.strip().upper()) - ord("A")
    return index if 0 <= index < 26 else -1


def _to_item(
    row: db.ExtractedQuestion,
    document_title: str,
    options: list[str],
    answer: db.ExtractedAnswer | None,
    corrected: bool,
    subjects: list[dict],
) -> dict:
    correct_index = _correct_index(answer)
    return {
        "question_id": str(row.id),
        "document_id": str(row.document_id),
        "document_title": document_title,
        "number": row.question_number,
        "text": row.normalized_text,
        "options": options,
        "kind": "mcq" if options else "qa_pair",
        "correct_index": correct_index,
        "correct_letter": chr(65 + correct_index) if 0 <= correct_index < 26 else "",
        "answer_source": (answer.resolution_method or "") if answer else "",
        "confidence": answer.resolution_score if answer else None,
        "verified": bool(
            answer and answer.status in ("verified_explicit_key", "manually_verified")
        ),
        "inferred": _is_inferred(answer),
        "corrected": corrected,
        "status": row.validation_status,
        "answer_status": _answer_status(row.validation_status, answer),
        "page": (row.source_pages or [None])[0],
        "subjects": subjects,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _assemble(
    session: Session, rows: list[db.ExtractedQuestion], titles: dict[uuid.UUID, str]
) -> list[dict]:
    """Rows -> API items with one batched query per relation."""
    ids = [row.id for row in rows]
    options = _batch_options(session, ids)
    answers = _batch_answers(session, ids)
    corrected = _batch_corrected(session, ids)
    subjects = _batch_subjects(session, ids)
    return [
        _to_item(
            row,
            titles.get(row.document_id, ""),
            options.get(row.id, []),
            answers.get(row.id),
            row.id in corrected,
            subjects.get(row.id, []),
        )
        for row in rows
    ]


def _number_key(row: db.ExtractedQuestion) -> tuple[int, int]:
    """Printed-number order for one document's questions. Numeric
    numbers sort numerically; unnumbered rows sort last."""
    number = (row.question_number or "").strip()
    if number.isdigit():
        return (0, int(number))
    return (1, 0)


def _status_exists(status: str) -> object:
    """EXISTS clause for one ``?status=`` filter value."""
    qid = db.ExtractedQuestion.id
    if status == "answered":
        return exists().where(
            (db.ExtractedAnswer.question_id == qid)
            & (db.ExtractedAnswer.resolved_label.isnot(None))
        )
    if status == "unknown":
        return ~exists().where(
            (db.ExtractedAnswer.question_id == qid)
            & (db.ExtractedAnswer.resolved_label.isnot(None))
        )
    if status == "pending":
        return db.ExtractedQuestion.validation_status == "pending"
    if status == "inferred":
        return exists().where(
            (db.ExtractedAnswer.question_id == qid)
            & (
                (db.ExtractedAnswer.resolution_method.in_(_INFERRED))
                | (db.ExtractedAnswer.status.in_(_INFERRED))
            )
        )
    if status == "corrected":
        return exists().where(db.ManualCorrection.target_id == qid)
    # conflicting: a conflicting answer, or a question whose
    # conflict was resolved (validation_status conflict-resolved).
    return (db.ExtractedQuestion.validation_status == "conflict-resolved") | exists().where(
        (db.ExtractedAnswer.question_id == qid) & (db.ExtractedAnswer.status == "conflicting")
    )


def list_questions(
    session: Session,
    user: dict,
    *,
    q: str | None = None,
    document_id: str | None = None,
    status: str | None = None,
    subject_id: str | None = None,
    confidence_min: float | None = None,
    confidence_max: float | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """The question bank: all of one user's extracted questions,
    searchable and filterable. Never returns another user's rows."""
    user_uuid = uuid.UUID(user["id"])
    query = (
        session.query(db.ExtractedQuestion)
        .join(db.Document, db.Document.id == db.ExtractedQuestion.document_id)
        .filter(db.Document.user_id == user_uuid)
        .filter(db.Document.deleted_at.is_(None))
    )
    if document_id:
        query = query.filter(
            db.ExtractedQuestion.document_id == _parse_uuid(document_id, "Document not found.")
        )
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(
            db.ExtractedQuestion.normalized_text.ilike(f"%{escaped}%", escape="\\")
        )
    if status:
        if status not in BANK_STATUSES:
            raise ApiError(
                status_code=422,
                code="validation_error",
                message=f"status must be one of: {', '.join(BANK_STATUSES)}.",
            )
        query = query.filter(_status_exists(status))
    if subject_id:
        subject_uuid = _parse_uuid(subject_id, "Subject not found.")
        query = query.filter(
            exists().where(
                (db.QuestionSubject.question_id == db.ExtractedQuestion.id)
                & (db.QuestionSubject.subject_id == subject_uuid)
            )
        )
    if confidence_min is not None or confidence_max is not None:
        # EXISTS, not a join: a question with two answer rows must
        # still count once (corrections update the answer in place,
        # but the read path must not depend on that).
        cond = db.ExtractedAnswer.question_id == db.ExtractedQuestion.id
        if confidence_min is not None:
            cond = cond & (db.ExtractedAnswer.resolution_score >= confidence_min)
        if confidence_max is not None:
            cond = cond & (db.ExtractedAnswer.resolution_score <= confidence_max)
        query = query.filter(exists().where(cond))
    total = query.count()
    rows = query.order_by(db.ExtractedQuestion.created_at.desc()).offset(offset).limit(limit).all()
    titles = {
        row.id: row.title
        for row in session.query(db.Document)
        .filter(db.Document.user_id == user_uuid)
        .filter(db.Document.deleted_at.is_(None))
        .all()
    }
    return {
        "questions": _assemble(session, rows, titles),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_question(session: Session, user: dict, question_id: str) -> dict:
    """One question with its full evidence trail + correction
    history. 404 for unknown or another user's question."""
    row = _own_question(session, user["id"], _parse_uuid(question_id))
    document = session.query(db.Document).filter(db.Document.id == row.document_id).first()
    answer = _latest_answer(session, row.id)
    evidence: list[dict] = []
    if answer is not None:
        evidence = [
            {
                "detector": ev.detector or "",
                "source_type": ev.source_type,
                "value_normalized": ev.value_normalized,
                "page_number": ev.page_number,
                "detector_confidence": ev.detector_confidence,
                "artifact_ref": ev.artifact_ref,
            }
            for ev in session.query(db.AnswerEvidence)
            .filter(db.AnswerEvidence.answer_id == answer.id)
            .order_by(db.AnswerEvidence.created_at)
            .all()
        ]
    item = _assemble(session, [row], {row.document_id: document.title if document else ""})[0]
    item["evidence"] = evidence
    item["corrections"] = _correction_items(session, row.id)
    return item


def _correction_items(session: Session, question_id: uuid.UUID) -> list[dict]:
    rows = (
        session.query(db.ManualCorrection)
        .filter(db.ManualCorrection.target_id == question_id)
        .order_by(db.ManualCorrection.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(row.id),
            "field_name": row.field_name,
            "old_value": row.old_value,
            "new_value": row.new_value,
            "reason": row.reason,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def list_corrections(session: Session, user: dict, document_id: str, question_id: str) -> dict:
    """The audit trail for one question: every manual correction
    with old/new values, newest first. Originals are never edited
    — this list IS the history."""
    document = _own_document(session, user["id"], _parse_uuid(document_id, "Document not found."))
    row = _own_question(session, user["id"], _parse_uuid(question_id))
    if row.document_id != document.id:
        raise _not_found()
    corrections = _correction_items(session, row.id)
    return {"question_id": str(row.id), "corrections": corrections, "total": len(corrections)}


def list_document_questions(
    session: Session,
    user: dict,
    document_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """One document's extraction results: every stored question
    in printed-number order, with counts. Q&A pairs are NOT stored
    as question rows (Phase 1 store keeps their count only) — the
    ``qa_pairs`` count comes from the stored report and the UI
    shows it as a count, never as fake questions."""
    document = _own_document(session, user["id"], _parse_uuid(document_id, "Document not found."))
    rows = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.document_id == document.id)
        .all()
    )
    rows.sort(key=lambda r: (_number_key(r), r.created_at or datetime.min))
    items = _assemble(session, rows, {document.id: document.title})
    counts = {
        "questions": len(items),
        "answered": sum(1 for i in items if i["correct_index"] >= 0),
        "unknown": sum(1 for i in items if i["correct_index"] < 0),
        "pending": sum(1 for i in items if i["status"] == "pending"),
        "inferred": sum(1 for i in items if i["inferred"]),
        "corrected": sum(1 for i in items if i["corrected"]),
    }
    report = (
        session.query(db.ExtractionReport)
        .filter(db.ExtractionReport.document_id == document.id)
        .order_by(db.ExtractionReport.created_at.desc())
        .first()
    )
    qa_pairs = 0
    if report is not None and isinstance(report.summary, dict):
        raw = report.summary.get("qa_pairs")
        qa_pairs = raw if isinstance(raw, int) else 0
    return {
        "document_id": str(document.id),
        "questions": items[offset : offset + limit],
        "total": len(items),
        "limit": limit,
        "offset": offset,
        "counts": counts,
        "qa_pairs": qa_pairs,
    }


def list_subjects(session: Session) -> dict:
    """All active subjects with their topics (global reference
    data — no user filter). Uncategorised stays uncategorised:
    no question is auto-assigned."""
    subjects = (
        session.query(db.Subject)
        .filter(db.Subject.is_active.is_(True))
        .order_by(db.Subject.name)
        .all()
    )
    topics = session.query(db.Topic).order_by(db.Topic.name).all()
    by_subject: dict[uuid.UUID, list[dict]] = {}
    for topic in topics:
        by_subject.setdefault(topic.subject_id, []).append(
            {"id": str(topic.id), "name": topic.name, "slug": topic.slug}
        )
    return {
        "subjects": [
            {
                "id": str(subject.id),
                "name": subject.name,
                "slug": subject.slug,
                "description": subject.description,
                "topics": by_subject.get(subject.id, []),
            }
            for subject in subjects
        ],
        "total": len(subjects),
    }


def assign_subject(
    session: Session,
    user: dict,
    question_id: str,
    subject_id: str,
    topic_id: str | None = None,
) -> dict:
    """Manually assign a subject (optionally a topic) to one of
    the caller's questions. Idempotent: re-assigning the same
    subject returns the existing row. No auto-classification —
    only the user assigns."""
    row = _own_question(session, user["id"], _parse_uuid(question_id))
    subject_uuid = _parse_uuid(subject_id, "Subject not found.")
    subject = session.query(db.Subject).filter(db.Subject.id == subject_uuid).first()
    if subject is None or not subject.is_active:
        raise ApiError(status_code=404, code="not_found", message="Subject not found.")
    topic = None
    topic_uuid = None
    if topic_id:
        topic_uuid = _parse_uuid(topic_id, "Topic not found.")
        topic = session.query(db.Topic).filter(db.Topic.id == topic_uuid).first()
        if topic is None or topic.subject_id != subject.id:
            raise ApiError(status_code=404, code="not_found", message="Topic not found.")
    existing = (
        session.query(db.QuestionSubject)
        .filter(db.QuestionSubject.question_id == row.id)
        .filter(db.QuestionSubject.subject_id == subject.id)
        .filter(db.QuestionSubject.topic_id == topic_uuid)
        .first()
    )
    if existing is not None:
        return {
            "question_id": str(row.id),
            "subject_id": str(subject.id),
            "subject_name": subject.name,
            "subject_slug": subject.slug,
            "topic_id": str(topic.id) if topic else None,
            "topic_name": topic.name if topic else None,
            "already_assigned": True,
        }
    session.add(
        db.QuestionSubject(
            question_id=row.id,
            subject_id=subject.id,
            topic_id=topic_uuid,
            assigned_by=uuid.UUID(user["id"]),
            confidence="manual",
        )
    )
    session.commit()
    return {
        "question_id": str(row.id),
        "subject_id": str(subject.id),
        "subject_name": subject.name,
        "subject_slug": subject.slug,
        "topic_id": str(topic.id) if topic else None,
        "topic_name": topic.name if topic else None,
        "already_assigned": False,
    }


def unassign_subject(session: Session, user: dict, question_id: str, subject_id: str) -> dict:
    """Remove a subject assignment from one of the caller's
    questions. 404 when the assignment does not exist."""
    row = _own_question(session, user["id"], _parse_uuid(question_id))
    subject_uuid = _parse_uuid(subject_id, "Subject not found.")
    deleted = (
        session.query(db.QuestionSubject)
        .filter(db.QuestionSubject.question_id == row.id)
        .filter(db.QuestionSubject.subject_id == subject_uuid)
        .delete()
    )
    if deleted == 0:
        raise ApiError(status_code=404, code="not_found", message="Subject assignment not found.")
    session.commit()
    return {"question_id": str(row.id), "subject_id": str(subject_uuid), "removed": True}
