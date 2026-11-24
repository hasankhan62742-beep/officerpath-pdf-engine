# OfficerPath AI — Phase 2, M8
# Results + student analytics (GAP-7) and question collections
# (GAP-8: bookmarks + mistake notebook).
#
# Ownership: every query filters by the JWT's user id; another
# user's results/collections 404 (never leaks existence — the
# Phase 1 pattern). All numbers come from real engine-DB rows.
#
# Hard rules enforced here (never in the frontend):
# - Breakdowns come from SAVED attempts only: the test's
#   snapshots + the student's responses + the bank questions'
#   QuestionSubject links. A question with no subject link goes
#   under an honest "Uncategorised" bucket — a subject is NEVER
#   invented or force-assigned. Unknown snapshots (correct_index
#   -1) are excluded from every breakdown bucket (they are
#   counted in unknown_count on the result, never scored).
# - Subject/topic for one snapshot: the EARLIEST QuestionSubject
#   row for its bank question (by created_at) that carries a
#   subject — "first assignment wins". Deterministic, documented,
#   and provable.
# - Weak/strong areas derive from the subject breakdown only:
#   among NAMED subjects with >= 3 scored questions, the lowest
#   accuracy is weakest and the highest is strongest. The
#   "Uncategorised" bucket never counts as a subject here. When
#   no named subject has >= 3 scored questions, both are null —
#   the UI says so honestly instead of inventing a verdict.
# - Backfill: M7 stored subject_breakdown / topic_breakdown as
#   NULL. Reading a result recomputes them from the stored
#   snapshots + responses and persists them (recompute-on-read).
#   The stored row is the truth afterwards; nothing is
#   recomputed on every read once filled.
# - Retry: a NEW test (new template + session + snapshots) whose
#   snapshots are byte-identical copies of the original test's
#   snapshots. A retake never edits the original attempt.
# - Practice from mistakes: snapshots come from the ORIGINAL
#   attempt snapshots (the most recent submitted session where
#   the student answered that question incorrectly) — NOT the
#   live bank. A later bank correction never changes a practice
#   test.
# - Mistake rows are created by the submit flow, in the SAME
#   transaction as the result row, for incorrectly-answered
#   scored questions only. Correct, unattempted and unknown
#   questions create NO mistake row. A re-submit (idempotent)
#   creates no duplicate rows.
# - Bookmarking twice is idempotent-200 (returns the existing
#   row with already_exists: true) — the same convention as
#   assign_subject in M5. "mistake" rows cannot be created by
#   the collections API (422) — only the submit flow writes them.

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models as db
from app.services.questions import (
    _batch_answers,
    _batch_options,
    _correct_index,
    _own_question,
    _parse_uuid,
)
from app.services.tests import (
    _load_template_and_marking,
    _marking_to_dict,
    _own_session,
    _resolve_marking_config,
    _snapshot_dict,
    _test_to_dict,
)

#: Minimum scored questions in a subject before it can be
#: named a weak or strong area. Below this, the UI says there
#: is not enough data yet — never a verdict from 1-2 questions.
WEAK_STRONG_MIN_SCORED = 3

#: Honest bucket for scored questions with no subject/topic link.
UNCATEGORISED = "Uncategorised"

COLLECTION_TYPES = ("bookmark", "mistake", "custom")
MAX_NOTE_LENGTH = 2000
MAX_MISTAKE_TEST_QUESTIONS = 200


def _now() -> datetime:
    return datetime.now(UTC)


def _not_found(what: str = "Not found.") -> ApiError:
    return ApiError(status_code=404, code="not_found", message=what)


def _validation(message: str) -> ApiError:
    return ApiError(status_code=422, code="validation_error", message=message)


def _load_session_or_404(session: Session, user_uuid: uuid.UUID, test_id: str) -> db.TestSession:
    return _own_session(session, user_uuid, _parse_uuid(test_id))


def _session_snapshots(
    session: Session, session_row: db.TestSession
) -> list[db.TestQuestionSnapshot]:
    return (
        session.query(db.TestQuestionSnapshot)
        .filter(db.TestQuestionSnapshot.session_id == session_row.id)
        .order_by(db.TestQuestionSnapshot.position)
        .all()
    )


def _responses_for(session: Session, session_row: db.TestSession) -> list[db.StudentResponse]:
    return (
        session.query(db.StudentResponse)
        .filter(db.StudentResponse.session_id == session_row.id)
        .order_by(db.StudentResponse.updated_at)
        .all()
    )


def _existing_result(session: Session, session_row: db.TestSession) -> db.TestResult | None:
    return session.query(db.TestResult).filter(db.TestResult.session_id == session_row.id).first()


# ---------------------------------------------------------------------------
# Outcomes + breakdowns (pure over stored rows)
# ---------------------------------------------------------------------------


def _snapshot_outcomes(
    snapshots: list[db.TestQuestionSnapshot],
    responses: list[db.StudentResponse],
) -> list[dict]:
    """One outcome per snapshot: status is correct / incorrect /
    unattempted / unknown (unknown = correct_index -1, never
    scored). ``selected_index`` None means unattempted."""
    by_snapshot = {str(row.snapshot_id): row for row in responses}
    outcomes = []
    for snap in snapshots:
        response = by_snapshot.get(str(snap.id))
        selected = response.selected_index if response is not None else None
        marked = response.marked_for_review if response is not None else False
        if snap.correct_index < 0:
            status = "unknown"
        elif selected is None:
            status = "unattempted"
        elif selected == snap.correct_index:
            status = "correct"
        else:
            status = "incorrect"
        outcomes.append(
            {
                "snapshot": snap,
                "selected_index": selected,
                "marked_for_review": marked,
                "status": status,
            }
        )
    return outcomes


def _assignment_map(
    session: Session, question_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict | None]:
    """First-assignment-wins subject/topic per bank question:
    the earliest QuestionSubject row (by created_at) that
    carries a subject. Returns {question_id: assignment dict or
    None} — None means the question has no subject link at all
    and belongs in the Uncategorised bucket. Tie caveat: two
    assignments created within the same created_at second have
    no defined order — the question still counts exactly once,
    in exactly one of its real subjects; the tiebreak is the
    database's row order, never a fabricated subject."""
    ids = [qid for qid in question_ids if qid is not None]
    if not ids:
        return {}
    rows = (
        session.query(db.QuestionSubject)
        .filter(db.QuestionSubject.question_id.in_(ids))
        .order_by(db.QuestionSubject.created_at)
        .all()
    )
    first: dict[uuid.UUID, db.QuestionSubject] = {}
    for row in rows:
        if row.question_id not in first and row.subject_id is not None:
            first[row.question_id] = row
    subject_ids = {row.subject_id for row in first.values() if row.subject_id is not None}
    topic_ids = {row.topic_id for row in first.values() if row.topic_id is not None}
    subjects = (
        {
            row.id: row
            for row in session.query(db.Subject).filter(db.Subject.id.in_(subject_ids)).all()
        }
        if subject_ids
        else {}
    )
    topics = (
        {row.id: row for row in session.query(db.Topic).filter(db.Topic.id.in_(topic_ids)).all()}
        if topic_ids
        else {}
    )
    out: dict[uuid.UUID, dict | None] = {}
    for qid in ids:
        row = first.get(qid)
        if row is None:
            out[qid] = None
            continue
        subject = subjects.get(row.subject_id) if row.subject_id else None
        topic = topics.get(row.topic_id) if row.topic_id else None
        out[qid] = {
            "subject_id": str(row.subject_id) if row.subject_id else None,
            "subject_name": subject.name if subject else None,
            "subject_slug": subject.slug if subject else None,
            "topic_id": str(row.topic_id) if row.topic_id else None,
            "topic_name": topic.name if topic else None,
            "topic_slug": topic.slug if topic else None,
        }
    return out


def _empty_bucket(key: str, name: str, slug: str | None) -> dict:
    return {
        "key": key,
        "name": name,
        "slug": slug,
        "scored": 0,
        "correct": 0,
        "incorrect": 0,
        "unattempted": 0,
        "marks": 0.0,
        "max_marks": 0.0,
        "accuracy": None,
    }


def compute_breakdowns(
    session: Session,
    snapshots: list[db.TestQuestionSnapshot],
    responses: list[db.StudentResponse],
    marking: db.MarkingConfig,
) -> dict:
    """Subject + topic breakdowns + weak/strong areas, from SAVED
    attempts only. Unknown snapshots are excluded from every
    bucket. Marks use Decimal arithmetic, rounded to 2dp.
    Accuracy is correct/scored * 100 (2dp); a bucket exists only
    when it holds >= 1 scored question, so accuracy is never
    null inside a returned bucket."""
    outcomes = _snapshot_outcomes(snapshots, responses)
    question_ids = [o["snapshot"].question_id for o in outcomes]
    assignments = _assignment_map(session, question_ids)
    cm = Decimal(str(marking.correct_marks))
    im = Decimal(str(marking.incorrect_marks))
    um = Decimal(str(marking.unattempted_marks))

    subject_buckets: dict[str, dict] = {}
    topic_buckets: dict[str, dict] = {}

    def _bucket(buckets: dict[str, dict], key: str, name: str, slug: str | None) -> dict:
        bucket = buckets.get(key)
        if bucket is None:
            bucket = _empty_bucket(key, name, slug)
            buckets[key] = bucket
        return bucket

    for outcome in outcomes:
        if outcome["status"] == "unknown":
            continue
        snap = outcome["snapshot"]
        assignment = assignments.get(snap.question_id) if snap.question_id else None
        if assignment and assignment["subject_name"]:
            s_key, s_name, s_slug = (
                assignment["subject_id"],
                assignment["subject_name"],
                assignment["subject_slug"],
            )
        else:
            s_key, s_name, s_slug = "uncategorised", UNCATEGORISED, None
        if assignment and assignment["topic_name"]:
            t_key, t_name, t_slug = (
                assignment["topic_id"],
                assignment["topic_name"],
                assignment["topic_slug"],
            )
        else:
            t_key, t_name, t_slug = "uncategorised", UNCATEGORISED, None
        if outcome["status"] == "correct":
            mark = cm
        elif outcome["status"] == "incorrect":
            mark = im
        else:
            mark = um
        for bucket in (
            _bucket(subject_buckets, s_key, s_name, s_slug),
            _bucket(topic_buckets, t_key, t_name, t_slug),
        ):
            bucket["scored"] += 1
            bucket[outcome["status"]] += 1
            bucket["marks"] = float(
                (Decimal(str(bucket["marks"])) + mark).quantize(Decimal("0.01"))
            )
            bucket["max_marks"] = float(
                (Decimal(str(bucket["max_marks"])) + cm).quantize(Decimal("0.01"))
            )

    def _finalise(buckets: dict[str, dict]) -> list[dict]:
        out = []
        for bucket in buckets.values():
            scored = bucket["scored"]
            if scored:
                accuracy = (Decimal(bucket["correct"]) / Decimal(scored) * Decimal("100")).quantize(
                    Decimal("0.01")
                )
                bucket["accuracy"] = float(accuracy)
            else:
                bucket["accuracy"] = None
            out.append(bucket)
        # Named buckets first (alphabetical), Uncategorised last.
        out.sort(key=lambda b: (b["name"] == UNCATEGORISED, b["name"]))
        return out

    subjects = _finalise(subject_buckets)
    topics = _finalise(topic_buckets)

    named = [
        b for b in subjects if b["name"] != UNCATEGORISED and b["scored"] >= WEAK_STRONG_MIN_SCORED
    ]
    weakest = None
    strongest = None
    if named:
        weakest_row = min(named, key=lambda b: (b["accuracy"], b["name"]))
        strongest_row = max(named, key=lambda b: (b["accuracy"], b["name"]))
        weakest = {
            "subject_name": weakest_row["name"],
            "accuracy": weakest_row["accuracy"],
            "scored": weakest_row["scored"],
        }
        strongest = {
            "subject_name": strongest_row["name"],
            "accuracy": strongest_row["accuracy"],
            "scored": strongest_row["scored"],
        }
    return {
        "subject_breakdown": subjects,
        "topic_breakdown": topics,
        "weak_areas": [weakest] if weakest else [],
        "strong_areas": [strongest] if strongest else [],
    }


def ensure_breakdowns(session: Session, session_row: db.TestSession, result: db.TestResult) -> dict:
    """Backfill for M7 rows stored with NULL breakdowns: compute
    from the stored snapshots + responses and persist. Once
    filled, the stored row is returned unchanged — no recompute
    on every read."""
    if result.subject_breakdown is not None and result.topic_breakdown is not None:
        return {
            "subject_breakdown": result.subject_breakdown,
            "topic_breakdown": result.topic_breakdown,
        }
    _, marking = _load_template_and_marking(session, session_row)
    snapshots = _session_snapshots(session, session_row)
    responses = _responses_for(session, session_row)
    computed = compute_breakdowns(session, snapshots, responses, marking)
    result.subject_breakdown = computed["subject_breakdown"]
    result.topic_breakdown = computed["topic_breakdown"]
    session.commit()
    session.refresh(result)
    return {
        "subject_breakdown": result.subject_breakdown,
        "topic_breakdown": result.topic_breakdown,
    }


def _weak_strong_from_breakdown(subject_breakdown: list | None) -> tuple[list, list]:
    """Weak/strong areas derived from a STORED breakdown (same
    rule as compute_breakdowns: named subjects, >= 3 scored)."""
    if not subject_breakdown:
        return [], []
    named = [
        b
        for b in subject_breakdown
        if b.get("name") != UNCATEGORISED and (b.get("scored") or 0) >= WEAK_STRONG_MIN_SCORED
    ]
    if not named:
        return [], []
    weakest_row = min(named, key=lambda b: (b.get("accuracy"), b.get("name")))
    strongest_row = max(named, key=lambda b: (b.get("accuracy"), b.get("name")))
    weakest = [
        {
            "subject_name": weakest_row["name"],
            "accuracy": weakest_row["accuracy"],
            "scored": weakest_row["scored"],
        }
    ]
    strongest = [
        {
            "subject_name": strongest_row["name"],
            "accuracy": strongest_row["accuracy"],
            "scored": strongest_row["scored"],
        }
    ]
    return weakest, strongest


# ---------------------------------------------------------------------------
# Mistake rows (called by the submit flow, same transaction)
# ---------------------------------------------------------------------------


def record_mistakes(
    session: Session,
    user_uuid: uuid.UUID,
    incorrect_question_ids: list[uuid.UUID | None],
) -> int:
    """Insert 'mistake' collection rows for incorrectly-answered
    scored questions. Skips None ids (snapshot whose bank
    question was deleted) and rows that already exist. The
    caller owns the commit — this runs inside the submit
    transaction. Returns the number of rows inserted."""
    ids = sorted({qid for qid in incorrect_question_ids if qid is not None})
    if not ids:
        return 0
    existing = {
        row.question_id
        for row in session.query(db.StudentQuestionCollection)
        .filter(db.StudentQuestionCollection.user_id == user_uuid)
        .filter(db.StudentQuestionCollection.collection_type == "mistake")
        .filter(db.StudentQuestionCollection.question_id.in_(ids))
        .all()
    }
    inserted = 0
    for qid in ids:
        if qid in existing:
            continue
        session.add(
            db.StudentQuestionCollection(
                user_id=user_uuid,
                question_id=qid,
                collection_type="mistake",
                note=None,
            )
        )
        inserted += 1
    return inserted


# ---------------------------------------------------------------------------
# Result reads (detail + history)
# ---------------------------------------------------------------------------


def _base_result_dict(
    row: db.TestResult, session_row: db.TestSession, marking: db.MarkingConfig
) -> dict:
    return {
        "result_id": str(row.id),
        "test_id": str(session_row.id),
        "template_id": str(session_row.template_id) if session_row.template_id else None,
        "title": session_row.title,
        "status": session_row.status,
        "total_questions": row.total_questions,
        "correct": row.correct_count,
        "incorrect": row.incorrect_count,
        "unattempted": row.unattempted_count,
        "unknown_count": row.unknown_count,
        "total_marks": float(row.total_marks),
        "max_marks": float(row.max_marks),
        "percentage": float(row.percentage),
        "time_taken_seconds": row.time_taken_seconds,
        "marking_config": _marking_to_dict(marking),
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
    }


def _review_items(
    session: Session,
    user_uuid: uuid.UUID,
    snapshots: list[db.TestQuestionSnapshot],
    responses: list[db.StudentResponse],
) -> list[dict]:
    """Per-question review: ONLY what the engine stored — the
    snapshot text/options/correct answer, the student's selected
    option, the evidence source, and the stored verbatim
    explanation (M10). No explanations are invented: None means
    the source gave none. Unknown snapshots show as unknown,
    never correct/incorrect."""
    outcomes = _snapshot_outcomes(snapshots, responses)
    question_ids = [o["snapshot"].question_id for o in outcomes if o["snapshot"].question_id]
    collections: dict[uuid.UUID, dict] = {}
    if question_ids:
        rows = (
            session.query(db.StudentQuestionCollection)
            .filter(db.StudentQuestionCollection.user_id == user_uuid)
            .filter(db.StudentQuestionCollection.question_id.in_(question_ids))
            .all()
        )
        for row in rows:
            entry = collections.setdefault(row.question_id, {})
            if row.collection_type == "bookmark":
                entry["bookmark_id"] = str(row.id)
            if row.collection_type == "mistake":
                entry["is_mistake"] = True
    items = []
    for outcome in outcomes:
        snap = outcome["snapshot"]
        entry = collections.get(snap.question_id, {}) if snap.question_id else {}
        items.append(
            {
                "snapshot_id": str(snap.id),
                "question_id": str(snap.question_id) if snap.question_id else None,
                "position": snap.position,
                "question_text": snap.question_text,
                "options": snap.options,
                "correct_index": snap.correct_index,
                "selected_index": outcome["selected_index"],
                "marked_for_review": outcome["marked_for_review"],
                "status": outcome["status"],
                "answer_source": snap.answer_source,
                "explanation": snap.explanation,
                "source_document_id": (
                    str(snap.source_document_id) if snap.source_document_id else None
                ),
                "source_page": snap.source_page,
                "is_bookmarked": "bookmark_id" in entry,
                "bookmark_id": entry.get("bookmark_id"),
                "is_mistake": entry.get("is_mistake", False),
            }
        )
    return items


def get_result_detail(session: Session, user: dict, test_id: str) -> dict:
    """The full result: stored row + breakdowns (backfilled when
    an M7 row stored NULL) + weak/strong areas + per-question
    review. The numbers shown are the stored row, exactly."""
    user_uuid = uuid.UUID(user["id"])
    session_row = _load_session_or_404(session, user_uuid, test_id)
    result = _existing_result(session, session_row)
    if result is None:
        raise _not_found("No result yet — submit the test first.")
    _, marking = _load_template_and_marking(session, session_row)
    breakdowns = ensure_breakdowns(session, session_row, result)
    weak, strong = _weak_strong_from_breakdown(breakdowns["subject_breakdown"])
    snapshots = _session_snapshots(session, session_row)
    responses = _responses_for(session, session_row)
    detail = _base_result_dict(result, session_row, marking)
    detail["subject_breakdown"] = breakdowns["subject_breakdown"]
    detail["topic_breakdown"] = breakdowns["topic_breakdown"]
    detail["weak_areas"] = weak
    detail["strong_areas"] = strong
    detail["review"] = _review_items(session, user_uuid, snapshots, responses)
    return detail


def list_results(session: Session, user: dict, *, limit: int = 20, offset: int = 0) -> dict:
    """Test history, newest first. Breakdowns are shown as stored
    (an M7 row keeps NULL until its detail page backfills it —
    the list never fabricates a breakdown)."""
    user_uuid = uuid.UUID(user["id"])
    query = (
        session.query(db.TestResult)
        .filter(db.TestResult.user_id == user_uuid)
        .order_by(db.TestResult.submitted_at.desc(), db.TestResult.created_at.desc())
    )
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    items = []
    for row in rows:
        session_row = (
            session.query(db.TestSession).filter(db.TestSession.id == row.session_id).first()
        )
        if session_row is None:
            continue
        _, marking = _load_template_and_marking(session, session_row)
        item = _base_result_dict(row, session_row, marking)
        item["subject_breakdown"] = row.subject_breakdown
        item["topic_breakdown"] = row.topic_breakdown
        weak, strong = _weak_strong_from_breakdown(row.subject_breakdown)
        item["weak_areas"] = weak
        item["strong_areas"] = strong
        items.append(item)
    return {"results": items, "total": total, "limit": limit, "offset": offset}


# ---------------------------------------------------------------------------
# Retry + practice from mistakes
# ---------------------------------------------------------------------------


def _copy_snapshots_into_new_session(
    session: Session,
    user_uuid: uuid.UUID,
    source_snapshots: list[db.TestQuestionSnapshot],
    template: db.TestTemplate,
    marking: db.MarkingConfig,
    title: str,
    time_limit_seconds: int | None,
) -> db.TestSession:
    """Create a fresh session + byte-identical snapshot copies.
    Only the snapshot row ids are new — text, options, correct
    answer, evidence source, explanation, source links and
    positions are copied field by field from the source
    snapshots."""
    session_row = db.TestSession(
        user_id=user_uuid,
        template_id=template.id,
        title=title,
        question_count=len(source_snapshots),
        marking_config_id=marking.id,
        status="created",
        time_limit_seconds=time_limit_seconds,
    )
    session.add(session_row)
    session.flush()
    for source in source_snapshots:
        session.add(
            db.TestQuestionSnapshot(
                session_id=session_row.id,
                question_id=source.question_id,
                position=source.position,
                question_text=source.question_text,
                options=[dict(o) for o in (source.options or [])],
                correct_index=source.correct_index,
                answer_source=source.answer_source,
                explanation=source.explanation,
                source_document_id=source.source_document_id,
                source_page=source.source_page,
            )
        )
    return session_row


def _new_test_detail(
    session: Session,
    session_row: db.TestSession,
    template: db.TestTemplate,
    marking: db.MarkingConfig,
) -> dict:
    snapshots = _session_snapshots(session, session_row)
    detail = _test_to_dict(session_row, template, marking)
    # The new session is always "created" — the key is withheld
    # until it is submitted (same rule as get_test).
    detail["snapshots"] = [_snapshot_dict(row, include_key=False) for row in snapshots]
    detail["excluded_unknown"] = template.excluded_unknown
    detail["excluded_no_options"] = template.excluded_no_options
    return detail


def retry_test(session: Session, user: dict, test_id: str) -> dict:
    """Retake a SUBMITTED test as a brand-new test: same
    snapshots, fresh session, fresh result. Only submitted
    sessions can be retried — retrying a created or in-progress
    test is a 409 (it already has a live attempt to finish)."""
    user_uuid = uuid.UUID(user["id"])
    session_row = _load_session_or_404(session, user_uuid, test_id)
    if session_row.status != "submitted":
        raise ApiError(
            status_code=409,
            code="test_not_submitted",
            message=(
                f"Only a submitted test can be retried (this test is "
                f"{session_row.status!r}). Finish or submit the current "
                "attempt first."
            ),
        )
    template, marking = _load_template_and_marking(session, session_row)
    source_snapshots = _session_snapshots(session, session_row)
    new_template = db.TestTemplate(
        user_id=user_uuid,
        name=f"{template.name} (retry)",
        description=template.description,
        question_count=template.question_count,
        source_type=template.source_type,
        source_ids=template.source_ids,
        allow_repetition=template.allow_repetition,
        include_unknown=template.include_unknown,
        selection_seed=None,
        excluded_unknown=template.excluded_unknown,
        excluded_no_options=template.excluded_no_options,
        marking_config_id=marking.id,
    )
    session.add(new_template)
    session.flush()
    new_session = _copy_snapshots_into_new_session(
        session,
        user_uuid,
        source_snapshots,
        new_template,
        marking,
        new_template.name,
        session_row.time_limit_seconds,
    )
    session.commit()
    detail = _new_test_detail(session, new_session, new_template, marking)
    detail["retried_from_test_id"] = str(session_row.id)
    return detail


def _latest_incorrect_snapshot(
    session: Session, user_uuid: uuid.UUID, question_id: uuid.UUID
) -> db.TestQuestionSnapshot | None:
    """The snapshot from the most recent submitted session where
    this user answered this bank question INCORRECTLY. The
    practice test copies THAT frozen snapshot — never the live
    bank row — so a later bank correction cannot change it."""
    row = (
        session.query(db.TestQuestionSnapshot)
        .join(db.TestSession, db.TestSession.id == db.TestQuestionSnapshot.session_id)
        .join(
            db.StudentResponse,
            db.StudentResponse.snapshot_id == db.TestQuestionSnapshot.id,
        )
        .filter(db.TestSession.user_id == user_uuid)
        .filter(db.TestSession.status == "submitted")
        .filter(db.TestQuestionSnapshot.question_id == question_id)
        .filter(db.TestQuestionSnapshot.correct_index >= 0)
        .filter(db.StudentResponse.selected_index.is_not(None))
        .filter(db.StudentResponse.selected_index != db.TestQuestionSnapshot.correct_index)
        .order_by(db.TestSession.submitted_at.desc(), db.TestSession.created_at.desc())
        .first()
    )
    return row


def create_test_from_mistakes(session: Session, user: dict, payload: dict) -> dict:
    """Build a practice test from the student's mistake
    collection. Snapshots come from the ORIGINAL incorrect
    attempts (see _latest_incorrect_snapshot). Questions with
    no usable incorrect-attempt snapshot are skipped and named
    in skipped_question_ids — never silently dropped, never
    invented from the live bank."""
    user_uuid = uuid.UUID(user["id"])
    name = (payload.get("name") or "").strip()
    if not name:
        raise _validation("Test name is required.")
    if len(name) > 200:
        raise _validation("Test name must be at most 200 characters.")
    time_limit = payload.get("time_limit_seconds")
    if time_limit is not None and (
        not isinstance(time_limit, int)
        or isinstance(time_limit, bool)
        or not (60 <= time_limit <= 86400)
    ):
        raise _validation("time_limit_seconds must be between 60 and 86400 when set.")
    raw_ids = payload.get("question_ids")
    if raw_ids is not None and not isinstance(raw_ids, list):
        raise _validation("question_ids must be a list of question ids.")
    if raw_ids:
        requested = [_parse_uuid(raw, "Question not found.") for raw in raw_ids]
        # Only the caller's own mistake rows may be practised.
        owned = {
            row.question_id
            for row in session.query(db.StudentQuestionCollection)
            .filter(db.StudentQuestionCollection.user_id == user_uuid)
            .filter(db.StudentQuestionCollection.collection_type == "mistake")
            .filter(db.StudentQuestionCollection.question_id.in_(requested))
            .all()
        }
        wanted = [qid for qid in requested if qid in owned]
        if not wanted:
            raise ApiError(
                status_code=422,
                code="no_mistakes",
                message="None of the requested questions are in your mistake notebook.",
            )
    else:
        rows = (
            session.query(db.StudentQuestionCollection)
            .filter(db.StudentQuestionCollection.user_id == user_uuid)
            .filter(db.StudentQuestionCollection.collection_type == "mistake")
            .order_by(db.StudentQuestionCollection.created_at.desc())
            .limit(MAX_MISTAKE_TEST_QUESTIONS)
            .all()
        )
        wanted = [row.question_id for row in rows]
        if not wanted:
            raise ApiError(
                status_code=422,
                code="no_mistakes",
                message="Your mistake notebook is empty — answer a test first.",
            )
    marking = _resolve_marking_config(
        session, payload.get("marking_config_id"), payload.get("marking")
    )
    source_snapshots: list[db.TestQuestionSnapshot] = []
    skipped: list[str] = []
    for qid in wanted:
        snap = _latest_incorrect_snapshot(session, user_uuid, qid)
        if snap is None:
            skipped.append(str(qid))
            continue
        source_snapshots.append(snap)
    if not source_snapshots:
        raise ApiError(
            status_code=422,
            code="no_mistakes",
            message=(
                "No mistake question has a usable incorrect attempt to "
                "practise from — the original attempts may have been "
                "removed. Skipped: " + ", ".join(skipped)
            ),
        )
    template = db.TestTemplate(
        user_id=user_uuid,
        name=name,
        description=None,
        question_count=len(source_snapshots),
        source_type="mistakes",
        source_ids={"question_ids": [str(s.question_id) for s in source_snapshots]},
        allow_repetition=False,
        include_unknown=False,
        selection_seed=None,
        excluded_unknown=0,
        excluded_no_options=0,
        marking_config_id=marking.id,
    )
    session.add(template)
    session.flush()
    new_session = _copy_snapshots_into_new_session(
        session,
        user_uuid,
        source_snapshots,
        template,
        marking,
        name,
        time_limit,
    )
    session.commit()
    detail = _new_test_detail(session, new_session, template, marking)
    detail["skipped_question_ids"] = skipped
    return detail


# ---------------------------------------------------------------------------
# Collections (bookmarks / mistakes / custom)
# ---------------------------------------------------------------------------


def _collection_to_dict(
    session: Session, row: db.StudentQuestionCollection, document_titles: dict
) -> dict:
    question = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.id == row.question_id)
        .first()
    )
    question_data = None
    if question is not None:
        options = _batch_options(session, [question.id]).get(question.id, [])
        answers = _batch_answers(session, [question.id])
        answer = answers.get(question.id)
        question_data = {
            "question_id": str(question.id),
            "document_id": str(question.document_id),
            "document_title": document_titles.get(question.document_id, ""),
            "number": question.question_number,
            "text": question.normalized_text,
            "options": options,
            "correct_index": _correct_index(answer),
            "answer_source": answer.resolution_method if answer else "",
            # Stored verbatim explanation from the bank (M10).
            # None = the source gave none; the UI shows nothing.
            "explanation": question.explanation,
        }
    return {
        "id": str(row.id),
        "question_id": str(row.question_id),
        "collection_type": row.collection_type,
        "note": row.note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "question": question_data,
    }


def list_collections(
    session: Session,
    user: dict,
    *,
    collection_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """The student's own collection rows, newest first, with the
    bank question attached. Filter by collection_type when given
    (mistake / bookmark / custom)."""
    user_uuid = uuid.UUID(user["id"])
    if collection_type is not None and collection_type not in COLLECTION_TYPES:
        raise _validation(f"collection_type must be one of: {', '.join(COLLECTION_TYPES)}.")
    query = (
        session.query(db.StudentQuestionCollection)
        .filter(db.StudentQuestionCollection.user_id == user_uuid)
        .order_by(db.StudentQuestionCollection.created_at.desc())
    )
    if collection_type is not None:
        query = query.filter(db.StudentQuestionCollection.collection_type == collection_type)
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    document_titles = {
        row.id: row.title
        for row in session.query(db.Document)
        .filter(db.Document.user_id == user_uuid)
        .filter(db.Document.deleted_at.is_(None))
        .all()
    }
    return {
        "collections": [_collection_to_dict(session, row, document_titles) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def create_collection(session: Session, user: dict, payload: dict) -> dict:
    """Bookmark (or file a custom entry for) one of the caller's
    questions. Idempotent: bookmarking twice returns the
    existing row with already_exists: true (200, never 409) —
    the same convention as assign_subject in M5. 'mistake' rows
    cannot be created here (422) — only the submit flow writes
    them."""
    user_uuid = uuid.UUID(user["id"])
    collection_type = payload.get("collection_type")
    if collection_type not in ("bookmark", "custom"):
        raise _validation(
            "collection_type must be 'bookmark' or 'custom' here — "
            "'mistake' rows are created by the submit flow only."
        )
    question_id = payload.get("question_id")
    if not isinstance(question_id, str) or not question_id:
        raise _validation("question_id is required.")
    question = _own_question(session, user["id"], _parse_uuid(question_id))
    note = payload.get("note")
    if note is not None:
        if not isinstance(note, str):
            raise _validation("note must be a string.")
        note = note.strip() or None
        if note is not None and len(note) > MAX_NOTE_LENGTH:
            raise _validation(f"note must be at most {MAX_NOTE_LENGTH} characters.")
    existing = (
        session.query(db.StudentQuestionCollection)
        .filter(db.StudentQuestionCollection.user_id == user_uuid)
        .filter(db.StudentQuestionCollection.question_id == question.id)
        .filter(db.StudentQuestionCollection.collection_type == collection_type)
        .first()
    )
    document_titles = {
        row.id: row.title
        for row in session.query(db.Document)
        .filter(db.Document.user_id == user_uuid)
        .filter(db.Document.deleted_at.is_(None))
        .all()
    }
    if existing is not None:
        out = _collection_to_dict(session, existing, document_titles)
        out["already_exists"] = True
        return out
    row = db.StudentQuestionCollection(
        user_id=user_uuid,
        question_id=question.id,
        collection_type=collection_type,
        note=note,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    out = _collection_to_dict(session, row, document_titles)
    out["already_exists"] = False
    return out


def update_collection_note(session: Session, user: dict, collection_id: str, payload: dict) -> dict:
    """Edit the personal note on one of the caller's collection
    entries (bookmark or mistake). Null clears the note."""
    user_uuid = uuid.UUID(user["id"])
    row = (
        session.query(db.StudentQuestionCollection)
        .filter(db.StudentQuestionCollection.id == _parse_uuid(collection_id))
        .filter(db.StudentQuestionCollection.user_id == user_uuid)
        .first()
    )
    if row is None:
        raise _not_found("Collection entry not found.")
    note = payload.get("note")
    if note is not None:
        if not isinstance(note, str):
            raise _validation("note must be a string.")
        note = note.strip() or None
        if note is not None and len(note) > MAX_NOTE_LENGTH:
            raise _validation(f"note must be at most {MAX_NOTE_LENGTH} characters.")
    row.note = note
    session.commit()
    session.refresh(row)
    document_titles = {
        doc.id: doc.title
        for doc in session.query(db.Document)
        .filter(db.Document.user_id == user_uuid)
        .filter(db.Document.deleted_at.is_(None))
        .all()
    }
    return _collection_to_dict(session, row, document_titles)


def delete_collection(session: Session, user: dict, collection_id: str) -> dict:
    """Delete one of the caller's collection entries (removes a
    bookmark or clears a mistake from the notebook)."""
    user_uuid = uuid.UUID(user["id"])
    row = (
        session.query(db.StudentQuestionCollection)
        .filter(db.StudentQuestionCollection.id == _parse_uuid(collection_id))
        .filter(db.StudentQuestionCollection.user_id == user_uuid)
        .first()
    )
    if row is None:
        raise _not_found("Collection entry not found.")
    session.delete(row)
    session.commit()
    return {"id": str(row.id), "deleted": True}
