# OfficerPath AI — PDF Engine (M16)
# Community-contributed questions ("Add Questions").
#
# Flow: a student submits a question + 4 options + correct
# answer + explanation + subject + source + paper; the row waits
# in ``community_questions`` (status pending) until an admin
# approves it, and the approval creates the real bank rows
# (ExtractedQuestion + options + answer + subject assignment)
# under the shared community document. Until approval the
# submission is invisible to every pool — students only ever
# see approved questions.
#
# Guards, in order: field validation (exactly 4 distinct
# non-empty options, exactly one correct, live subject, topic
# inside that subject) -> per-user daily cap (20/day) ->
# duplicate refusal (same question already submitted, or
# already in the bank for that subject — the refusal names the
# paper it came from when one is known). The contributor is
# never shown another student's email: only the display-name
# snapshot ("Submitted by ...").

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models as db

DAILY_LIMIT = 20
MAX_QUESTION_CHARS = 2000
MAX_OPTION_CHARS = 500
MAX_EXPLANATION_CHARS = 5000
MAX_SOURCE_CHARS = 500
MAX_PAPER_CHARS = 200
MAX_REVIEW_NOTE_CHARS = 1000

COMMUNITY_DOC_TITLE = "Community Questions"
COMMUNITY_DOC_STORAGE_PATH = "community/questions"
COMMUNITY_DOC_IMPORT_KIND = "community-questions"


def _validation(message: str) -> ApiError:
    return ApiError(status_code=422, code="validation_error", message=message)


def _duplicate(message: str) -> ApiError:
    return ApiError(status_code=409, code="duplicate", message=message)


def _not_found(what: str = "Submission not found.") -> ApiError:
    return ApiError(status_code=404, code="not_found", message=what)


def normalize_text(text: str) -> str:
    """Lowercase, collapsed whitespace — the duplicate key."""
    return re.sub(r"\s+", " ", text.strip().lower())


def fingerprint(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def display_name(session: Session, user: dict) -> str:
    """Profile full name, else the email local part, else
    "Student". A full email address is never a display name —
    it must never reach the UI."""
    user_id = user.get("id")
    if user_id:
        profile = (
            session.query(db.StudentProfile)
            .filter(db.StudentProfile.user_id == uuid.UUID(str(user_id)))
            .first()
        )
        if profile is not None and profile.full_name.strip():
            return profile.full_name.strip()
    email = (user.get("email") or "").strip()
    if "@" in email:
        local = email.split("@", 1)[0].strip()
        if local:
            return local
    return "Student"


def _subject_or_404(session: Session, subject_id: str) -> db.Subject:
    try:
        subject_uuid = uuid.UUID(subject_id)
    except (ValueError, AttributeError, TypeError):
        raise _not_found("Subject not found.") from None
    subject = session.query(db.Subject).filter(db.Subject.id == subject_uuid).first()
    if subject is None or not subject.is_active:
        raise _not_found("Subject not found.")
    return subject


def _topic_or_404(session: Session, topic_id: str, subject_id: uuid.UUID) -> db.Topic:
    try:
        topic_uuid = uuid.UUID(topic_id)
    except (ValueError, AttributeError, TypeError):
        raise _not_found("Section not found.") from None
    topic = session.query(db.Topic).filter(db.Topic.id == topic_uuid).first()
    if topic is None or topic.subject_id != subject_id:
        raise _not_found("Section not found.")
    return topic


def _clean_str(value: str | None, *, max_chars: int) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > max_chars:
        raise _validation(f"Text is too long (max {max_chars} characters).")
    return cleaned


def _validate_submission(payload: dict) -> dict:
    """Field validation. Returns cleaned values."""
    question = (payload.get("question") or "").strip()
    if not question:
        raise _validation("A question is required.")
    if len(question) > MAX_QUESTION_CHARS:
        raise _validation(f"Question is too long (max {MAX_QUESTION_CHARS} characters).")
    raw_options = payload.get("options")
    if not isinstance(raw_options, list) or len(raw_options) != 4:
        raise _validation("Exactly four options are required.")
    options = []
    for option in raw_options:
        text = (option or "").strip() if isinstance(option, str) else ""
        if not text:
            raise _validation("All four options must be non-empty.")
        if len(text) > MAX_OPTION_CHARS:
            raise _validation(f"Option is too long (max {MAX_OPTION_CHARS} characters).")
        options.append(text)
    lowered = [normalize_text(option) for option in options]
    if len(set(lowered)) != 4:
        raise _validation("The four options must all be different.")
    correct_index = payload.get("correct_index")
    if not isinstance(correct_index, int) or isinstance(correct_index, bool):
        raise _validation("A correct option (A-D) is required.")
    if correct_index < 0 or correct_index > 3:
        raise _validation("The correct option must be one of A, B, C or D.")
    explanation = _clean_str(payload.get("explanation"), max_chars=MAX_EXPLANATION_CHARS)
    source = _clean_str(payload.get("source"), max_chars=MAX_SOURCE_CHARS)
    paper = _clean_str(payload.get("paper"), max_chars=MAX_PAPER_CHARS)
    return {
        "question": question,
        "options": options,
        "correct_index": correct_index,
        "explanation": explanation,
        "source": source,
        "paper": paper,
    }


def _today_count(session: Session, contributor_id: uuid.UUID) -> int:
    """Submissions by this contributor today (UTC calendar day).
    Bounded: only the newest 25 rows are read, counted in
    Python — dialect-independent (SQLite stores naive UTC
    datetimes, Postgres timestamptz)."""
    now = datetime.now(UTC)
    rows = (
        session.query(db.CommunityQuestion)
        .filter(db.CommunityQuestion.contributor_id == contributor_id)
        .order_by(db.CommunityQuestion.created_at.desc())
        .limit(DAILY_LIMIT + 5)
        .all()
    )
    count = 0
    for row in rows:
        created = row.created_at
        if created is None:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if created.date() == now.date():
            count += 1
    return count


def _find_duplicate(
    session: Session, subject_id: uuid.UUID, fp: str, normalized: str
) -> tuple[str, str | None] | None:
    """(where, paper) when this question already exists for the
    subject — in the staging queue or in the bank. ``where`` is
    "submitted" (a pending/approved staging row) or "bank". The
    paper is the known paper of the existing copy, or None."""
    staged = (
        session.query(db.CommunityQuestion)
        .filter(
            db.CommunityQuestion.fingerprint == fp,
            db.CommunityQuestion.subject_id == subject_id,
            db.CommunityQuestion.status.in_(["pending", "approved"]),
        )
        .order_by(db.CommunityQuestion.created_at.desc())
        .first()
    )
    if staged is not None:
        return ("submitted", staged.paper)
    bank_row = (
        session.query(db.ExtractedQuestion)
        .join(db.Document, db.Document.id == db.ExtractedQuestion.document_id)
        .join(
            db.QuestionSubject,
            db.QuestionSubject.question_id == db.ExtractedQuestion.id,
        )
        .filter(
            db.Document.deleted_at.is_(None),
            db.QuestionSubject.subject_id == subject_id,
        )
        .filter(
            (db.ExtractedQuestion.content_fingerprint == fp)
            | (func.lower(db.ExtractedQuestion.normalized_text) == normalized)
        )
        .order_by(db.ExtractedQuestion.created_at.desc())
        .first()
    )
    if bank_row is not None:
        return ("bank", bank_row.paper)
    return None


def _subject_ref(
    session: Session, subject_id: uuid.UUID | None, topic_id: uuid.UUID | None
) -> dict:
    subject = (
        session.query(db.Subject).filter(db.Subject.id == subject_id).first()
        if subject_id is not None
        else None
    )
    topic = (
        session.query(db.Topic).filter(db.Topic.id == topic_id).first()
        if topic_id is not None
        else None
    )
    return {
        "subject_id": str(subject.id) if subject else None,
        "subject_name": subject.name if subject else None,
        "subject_slug": subject.slug if subject else None,
        "topic_id": str(topic.id) if topic else None,
        "topic_name": topic.name if topic else None,
    }


def _to_item(session: Session, row: db.CommunityQuestion) -> dict:
    return {
        "id": str(row.id),
        "question": row.question_text,
        "options": list(row.options or []),
        "correct_index": row.correct_index,
        "correct_letter": chr(65 + row.correct_index),
        "explanation": row.explanation,
        "subject": _subject_ref(session, row.subject_id, row.topic_id),
        "source": row.source,
        "paper": row.paper,
        "status": row.status,
        "review_note": row.review_note,
        "contributor_name": row.contributor_name,
        "bank_question_id": str(row.bank_question_id) if row.bank_question_id else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def submit_question(session: Session, user: dict, payload: dict) -> dict:
    """Validate -> daily cap -> duplicate refusal -> staging row
    (status pending). The question reaches the bank only through
    admin approval (see review)."""
    cleaned = _validate_submission(payload)
    subject_id = payload.get("subject_id")
    if not isinstance(subject_id, str) or not subject_id.strip():
        raise _validation("A subject is required.")
    subject = _subject_or_404(session, subject_id)
    topic = None
    topic_id = payload.get("topic_id")
    if topic_id:
        if not isinstance(topic_id, str):
            raise _validation("Section is invalid.")
        topic = _topic_or_404(session, topic_id, subject.id)
    contributor_id = uuid.UUID(str(user["id"]))
    if _today_count(session, contributor_id) >= DAILY_LIMIT:
        raise ApiError(
            status_code=429,
            code="rate_limited",
            message=(
                f"You can submit up to {DAILY_LIMIT} questions per day. Please try again tomorrow."
            ),
        )
    fp = fingerprint(cleaned["question"])
    normalized = normalize_text(cleaned["question"])
    duplicate = _find_duplicate(session, subject.id, fp, normalized)
    if duplicate is not None:
        where, paper = duplicate
        if where == "bank":
            detail = f" (paper: {paper})" if paper else ""
            raise _duplicate(f"This question is already in the {subject.name} bank{detail}.")
        detail = f" (paper: {paper})" if paper else ""
        raise _duplicate(
            f"This question was already submitted for {subject.name}{detail} "
            "and is waiting for review."
        )
    row = db.CommunityQuestion(
        contributor_id=contributor_id,
        contributor_name=display_name(session, user),
        question_text=cleaned["question"],
        options=cleaned["options"],
        correct_index=cleaned["correct_index"],
        explanation=cleaned["explanation"],
        subject_id=subject.id,
        topic_id=topic.id if topic else None,
        source=cleaned["source"],
        paper=cleaned["paper"],
        status="pending",
        fingerprint=fp,
    )
    session.add(row)
    session.commit()
    return {
        "id": str(row.id),
        "status": row.status,
        "contributor_name": row.contributor_name,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def list_mine(session: Session, user: dict, *, limit: int = 20, offset: int = 0) -> dict:
    """The caller's own submissions, newest first. Another
    student's submissions never appear here."""
    contributor_id = uuid.UUID(str(user["id"]))
    query = (
        session.query(db.CommunityQuestion)
        .filter(db.CommunityQuestion.contributor_id == contributor_id)
        .order_by(db.CommunityQuestion.created_at.desc())
    )
    total = query.count()
    rows = query.limit(limit).offset(offset).all()
    return {
        "items": [_to_item(session, row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def list_for_admin(
    session: Session,
    *,
    status: str | None = None,
    subject_id: str | None = None,
    search: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Review queue, pending first. Admins see every submission
    with its paper, source and contributor name — the paper is
    what lets the admin spot a repetition at review time."""
    query = session.query(db.CommunityQuestion).order_by(
        db.CommunityQuestion.status != "pending",
        db.CommunityQuestion.created_at.desc(),
    )
    if status is not None:
        if status not in ("pending", "approved", "rejected"):
            raise _validation("status must be pending, approved or rejected.")
        query = query.filter(db.CommunityQuestion.status == status)
    if subject_id is not None:
        query = query.filter(db.CommunityQuestion.subject_id == uuid.UUID(subject_id))
    if search:
        query = query.filter(db.CommunityQuestion.question_text.ilike(f"%{search}%"))
    total = query.count()
    rows = query.limit(limit).offset(offset).all()
    return {
        "items": [_to_item(session, row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _get_or_create_community_document(session: Session, admin_id: uuid.UUID) -> db.Document:
    """The one shared bank document community approvals write
    into. Found by its marker (title + storage path + metadata
    import_kind); created once, owned by the approving admin,
    shared to every student. Subject routing does not need one
    document per subject — the pool finds questions through
    question_subjects, not through documents."""
    candidates = (
        session.query(db.Document)
        .filter(
            db.Document.deleted_at.is_(None),
            db.Document.title == COMMUNITY_DOC_TITLE,
            db.Document.storage_path == COMMUNITY_DOC_STORAGE_PATH,
            db.Document.is_shared.is_(True),
        )
        .all()
    )
    for doc in candidates:
        metadata = doc.metadata_json or {}
        if isinstance(metadata, dict) and metadata.get("import_kind") == COMMUNITY_DOC_IMPORT_KIND:
            return doc
    doc = db.Document(
        user_id=admin_id,
        title=COMMUNITY_DOC_TITLE,
        storage_path=COMMUNITY_DOC_STORAGE_PATH,
        file_type="txt",
        file_size_bytes=0,
        page_count=None,
        content_hash=None,
        is_shared=True,
        metadata_json={"import_kind": COMMUNITY_DOC_IMPORT_KIND},
    )
    session.add(doc)
    session.flush()
    return doc


def review(
    session: Session, admin_user: dict, submission_id: str, *, approved: bool, note: str | None
) -> dict:
    """Approve (creates the bank rows) or reject (records the
    reason). Only a pending submission can be reviewed — a
    second review is refused, so an approval can never mint
    the same bank question twice."""
    try:
        row_id = uuid.UUID(submission_id)
    except (ValueError, AttributeError, TypeError):
        raise _not_found() from None
    row = session.query(db.CommunityQuestion).filter(db.CommunityQuestion.id == row_id).first()
    if row is None:
        raise _not_found()
    if row.status != "pending":
        raise ApiError(
            status_code=409,
            code="already_reviewed",
            message=f"This submission was already {row.status}.",
        )
    clean_note = _clean_str(note, max_chars=MAX_REVIEW_NOTE_CHARS) if note is not None else None
    admin_id = uuid.UUID(str(admin_user["id"]))
    now = datetime.now(UTC)
    if not approved:
        row.status = "rejected"
        row.review_note = clean_note
        row.reviewed_by = admin_id
        row.reviewed_at = now
        session.commit()
        return _to_item(session, row)
    doc = _get_or_create_community_document(session, admin_id)
    correct_letter = chr(65 + row.correct_index)
    bank_question = db.ExtractedQuestion(
        document_id=doc.id,
        question_number=None,
        original_text=row.question_text,
        normalized_text=row.question_text.strip(),
        explanation=row.explanation,
        extraction_method="community",
        validation_status="manually_verified",
        content_fingerprint=row.fingerprint,
        contributor_name=row.contributor_name,
        community_question_id=row.id,
        paper=row.paper,
    )
    session.add(bank_question)
    session.flush()
    for position, option_text in enumerate(row.options):
        session.add(
            db.QuestionOption(
                question_id=bank_question.id,
                original_label=chr(65 + position),
                normalized_label=chr(65 + position),
                label_inferred=False,
                original_text=option_text,
                normalized_text=option_text.strip(),
                position=position,
            )
        )
    session.add(
        db.ExtractedAnswer(
            question_id=bank_question.id,
            document_id=doc.id,
            status="manually_verified",
            resolved_label=correct_letter,
            resolution_method="community_contribution",
        )
    )
    session.add(
        db.QuestionSubject(
            question_id=bank_question.id,
            subject_id=row.subject_id,
            topic_id=row.topic_id,
            assigned_by=admin_id,
            confidence="manual",
        )
    )
    row.status = "approved"
    row.review_note = clean_note
    row.reviewed_by = admin_id
    row.reviewed_at = now
    row.bank_question_id = bank_question.id
    session.commit()
    return _to_item(session, row)
