# OfficerPath AI — Phase 2, M7
# Examination interface (GAP-6): start, session, answers, submit, result.
#
# Ownership: every query filters by the JWT's user id; another
# user's test answers 404 (never leaks existence — the Phase 1
# pattern). All numbers come from real engine-DB rows.
#
# Hard rules enforced here (never in the frontend):
# - Template → session: M6 creates template + session 1:1 at
#   build time — the session IS the test instance. Start
#   activates that same session (created → in_progress). No new
#   session row is created per attempt; a retake is a new test
#   (M8 handles retakes).
# - The timer anchor is ``server_started_at`` — set from the
#   SERVER clock at start, never from the browser. Remaining
#   time is computed on the server from that anchor + the time
#   limit. A test with no time limit returns remaining null,
#   honestly.
# - Answers are stored against SNAPSHOT ids, never live bank
#   question ids. One row per (session, snapshot) — every save
#   is an upsert.
# - Scoring is backend-only (M6's ``score_answers``). Unknown
#   snapshots (correct_index -1) are EXCLUDED from scoring and
#   recorded as ``unknown_count`` on the result — never scored
#   as wrong, never a 500.
# - Submit is idempotent: a second submit returns the SAME
#   result row (same id, same marks) — enforced by the UNIQUE
#   (session_id) constraint on test_results plus a re-read on
#   conflict.
# - ``time_taken_seconds`` comes from server timestamps
#   (submitted_at − server_started_at), never the browser.

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models as db
from app.services.questions import _parse_uuid
from app.services.results import compute_breakdowns, record_mistakes
from app.services.tests import (
    _load_template_and_marking,
    _marking_to_dict,
    _own_session,
    _snapshot_dict,
    score_answers,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _not_found(what: str = "Test not found.") -> ApiError:
    return ApiError(status_code=404, code="not_found", message=what)


def _conflict(code: str, message: str) -> ApiError:
    return ApiError(status_code=409, code=code, message=message)


def _validation(message: str) -> ApiError:
    return ApiError(status_code=422, code="validation_error", message=message)


def _deadline(session_row: db.TestSession) -> datetime | None:
    """The server-side expiry instant, or None for untimed tests."""
    if session_row.time_limit_seconds is None or session_row.server_started_at is None:
        return None
    started = session_row.server_started_at
    if started.tzinfo is None:  # SQLite returns naive datetimes
        started = started.replace(tzinfo=UTC)
    return started + timedelta(seconds=session_row.time_limit_seconds)


def _remaining_seconds(session_row: db.TestSession, now: datetime) -> int | None:
    """Server-computed remaining time. None = no time limit
    (honest, not a faked countdown). 0 once the test is over."""
    if session_row.time_limit_seconds is None:
        return None
    if session_row.status == "created":
        return session_row.time_limit_seconds
    if session_row.status in ("submitted", "expired", "abandoned"):
        return 0
    deadline = _deadline(session_row)
    if deadline is None:
        return None
    return max(0, int((deadline - now).total_seconds()))


def _check_expiry(session: Session, session_row: db.TestSession, now: datetime) -> bool:
    """Move an in-progress session past its deadline to
    ``expired`` (server-side, one commit). Returns True when the
    session is expired (was already, or just transitioned)."""
    if session_row.status != "in_progress":
        return session_row.status == "expired"
    deadline = _deadline(session_row)
    if deadline is None or now <= deadline:
        return False
    session_row.status = "expired"
    session_row.expires_at = deadline
    session.commit()
    return True


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


def _response_to_dict(row: db.StudentResponse) -> dict:
    return {
        "snapshot_id": str(row.snapshot_id),
        "selected_index": row.selected_index,
        "marked_for_review": row.marked_for_review,
        "answered_at": row.answered_at.isoformat() if row.answered_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _result_to_dict(
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


def _existing_result(session: Session, session_row: db.TestSession) -> db.TestResult | None:
    return session.query(db.TestResult).filter(db.TestResult.session_id == session_row.id).first()


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------


def start_test(session: Session, user: dict, test_id: str) -> dict:
    """Activate a created test: status created → in_progress,
    ``server_started_at`` from the SERVER clock. Starting an
    already-started or submitted test is a 409."""
    user_uuid = uuid.UUID(user["id"])
    session_row = _load_session_or_404(session, user_uuid, test_id)
    if session_row.status != "created":
        raise _conflict(
            "test_already_started",
            f"A test in status {session_row.status!r} cannot be started.",
        )
    now = _now()
    session_row.status = "in_progress"
    session_row.server_started_at = now
    session_row.started_at = now
    if session_row.time_limit_seconds is not None:
        session_row.expires_at = now + timedelta(seconds=session_row.time_limit_seconds)
    session.commit()
    _, marking = _load_template_and_marking(session, session_row)
    return {
        "test_id": str(session_row.id),
        "title": session_row.title,
        "status": session_row.status,
        "time_limit_seconds": session_row.time_limit_seconds,
        "server_started_at": session_row.server_started_at.isoformat(),
        "expires_at": session_row.expires_at.isoformat() if session_row.expires_at else None,
        "remaining_seconds": _remaining_seconds(session_row, now),
        "marking_config": _marking_to_dict(marking),
    }


# ---------------------------------------------------------------------------
# Session (snapshots + saved responses + server remaining time)
# ---------------------------------------------------------------------------


def get_exam_session(session: Session, user: dict, test_id: str) -> dict:
    """The exam state: snapshots in test order, saved responses,
    session status, and the SERVER-computed remaining seconds.
    A session past its deadline flips to ``expired`` here — the
    exam page then locks and submits what was saved."""
    user_uuid = uuid.UUID(user["id"])
    session_row = _load_session_or_404(session, user_uuid, test_id)
    now = _now()
    _check_expiry(session, session_row, now)
    _, marking = _load_template_and_marking(session, session_row)
    snapshots = _session_snapshots(session, session_row)
    responses = _responses_for(session, session_row)
    return {
        "test_id": str(session_row.id),
        "title": session_row.title,
        "status": session_row.status,
        "time_limit_seconds": session_row.time_limit_seconds,
        "server_started_at": (
            session_row.server_started_at.isoformat() if session_row.server_started_at else None
        ),
        "expires_at": session_row.expires_at.isoformat() if session_row.expires_at else None,
        "remaining_seconds": _remaining_seconds(session_row, now),
        "server_time": now.isoformat(),
        "marking_config": _marking_to_dict(marking),
        "snapshots": [_snapshot_dict(row) for row in snapshots],
        "responses": [_response_to_dict(row) for row in responses],
    }


# ---------------------------------------------------------------------------
# Answers (upsert)
# ---------------------------------------------------------------------------


def save_answers(session: Session, user: dict, test_id: str, payload: dict) -> dict:
    """Upsert one or more answers. Only while the session is
    ``in_progress`` AND within the time limit — an answer after
    expiry is a 409 and NOTHING is stored. Each item names a
    snapshot in THIS test (404 otherwise); ``selected_index``
    must be null (clear) or a valid option index for that
    snapshot (422 otherwise)."""
    user_uuid = uuid.UUID(user["id"])
    session_row = _load_session_or_404(session, user_uuid, test_id)
    now = _now()
    if session_row.status == "submitted":
        raise _conflict("test_already_submitted", "This test is already submitted.")
    if session_row.status == "expired":
        raise _conflict(
            "time_expired", "The time for this test has expired — no more answers can be saved."
        )
    if session_row.status != "in_progress":
        raise _conflict(
            "test_not_started", f"A test in status {session_row.status!r} cannot take answers."
        )
    if _check_expiry(session, session_row, now):
        raise _conflict(
            "time_expired", "The time for this test has expired — no more answers can be saved."
        )
    items = payload.get("answers")
    if not isinstance(items, list) or not items:
        raise _validation("answers must be a non-empty list.")
    snapshots = {str(row.id): row for row in _session_snapshots(session, session_row)}
    saved: list[db.StudentResponse] = []
    # A batch may name the same snapshot twice (e.g. an answer plus a
    # mark-for-review flip for the same question). The loop below creates
    # a pending row per item, and a second item would query before the
    # first row is committed — so it would create a second pending row
    # and hit UNIQUE(session_id, snapshot_id) at commit (500). Track
    # rows created in THIS batch and reuse them; last item wins.
    seen: dict[str, db.StudentResponse] = {}
    for item in items:
        if not isinstance(item, dict):
            raise _validation("Each answer must be an object.")
        snapshot_id = item.get("snapshot_id")
        if not isinstance(snapshot_id, str) or snapshot_id not in snapshots:
            raise _not_found("Snapshot not found in this test.")
        if "selected_index" not in item:
            raise _validation("selected_index is required (null clears the answer).")
        selected = item["selected_index"]
        snapshot = snapshots[snapshot_id]
        option_count = len(snapshot.options or [])
        if selected is not None and (
            not isinstance(selected, int)
            or isinstance(selected, bool)
            or not (0 <= selected < option_count)
        ):
            raise _validation(
                f"selected_index must be null or between 0 and {option_count - 1} "
                f"for this question (got {selected!r})."
            )
        marked = item.get("marked_for_review")
        if marked is not None and not isinstance(marked, bool):
            raise _validation("marked_for_review must be a boolean.")
        row = seen.get(snapshot_id)
        if row is None:
            row = (
                session.query(db.StudentResponse)
                .filter(db.StudentResponse.session_id == session_row.id)
                .filter(db.StudentResponse.snapshot_id == uuid.UUID(snapshot_id))
                .first()
            )
            if row is None:
                row = db.StudentResponse(
                    session_id=session_row.id,
                    snapshot_id=uuid.UUID(snapshot_id),
                    user_id=user_uuid,
                    selected_index=selected,
                    marked_for_review=bool(marked) if marked is not None else False,
                    answered_at=now if selected is not None else None,
                )
                session.add(row)
            seen[snapshot_id] = row
        # Apply this item's values whether the row is new, pre-existing,
        # or already seen in this batch (last item wins).
        row.selected_index = selected
        if marked is not None:
            row.marked_for_review = marked
        if selected is not None:
            row.answered_at = now
        if row not in saved:
            saved.append(row)
    session.commit()
    for row in saved:
        session.refresh(row)
    remaining = _remaining_seconds(session_row, _now())
    return {
        "test_id": str(session_row.id),
        "status": session_row.status,
        "remaining_seconds": remaining,
        "saved": [_response_to_dict(row) for row in saved],
    }


# ---------------------------------------------------------------------------
# Submit (server-side marking, idempotent)
# ---------------------------------------------------------------------------


def submit_test(session: Session, user: dict, test_id: str) -> dict:
    """Submit: compute marks server-side and write exactly ONE
    test_results row. A second submit returns the SAME row.
    Unknown snapshots are excluded from scoring and counted as
    unknown_count — never scored as wrong, never a 500.
    ``time_taken_seconds`` comes from server timestamps."""
    user_uuid = uuid.UUID(user["id"])
    session_row = _load_session_or_404(session, user_uuid, test_id)
    now = _now()
    existing = _existing_result(session, session_row)
    if existing is not None:
        _, marking = _load_template_and_marking(session, session_row)
        return _result_to_dict(existing, session_row, marking)
    if session_row.status == "created":
        raise _conflict("test_not_started", "This test has not been started yet.")
    if session_row.status not in ("in_progress", "expired"):
        raise _conflict(
            "test_already_submitted",
            f"A test in status {session_row.status!r} cannot be submitted.",
        )
    _check_expiry(session, session_row, now)
    _, marking = _load_template_and_marking(session, session_row)
    snapshots = _session_snapshots(session, session_row)
    responses = {str(row.snapshot_id): row for row in _responses_for(session, session_row)}
    scored_items: list[dict] = []
    unknown_count = 0
    for snap in snapshots:
        if snap.correct_index < 0:
            unknown_count += 1
            continue
        response = responses.get(str(snap.id))
        scored_items.append(
            {
                "correct_index": snap.correct_index,
                "selected_index": response.selected_index if response is not None else None,
            }
        )
    score = score_answers(
        scored_items,
        correct_marks=marking.correct_marks,
        incorrect_marks=marking.incorrect_marks,
        unattempted_marks=marking.unattempted_marks,
    )
    # M8: subject/topic breakdowns from the SAVED attempt, and
    # mistake rows for incorrectly-answered scored questions —
    # both in the SAME transaction as the result row, so a submit
    # never leaves a result without its breakdowns or its
    # mistakes.
    breakdowns = compute_breakdowns(session, snapshots, list(responses.values()), marking)
    incorrect_question_ids = [
        snap.question_id
        for snap in snapshots
        if snap.correct_index >= 0
        and (responses.get(str(snap.id)) is not None)
        and responses[str(snap.id)].selected_index is not None
        and responses[str(snap.id)].selected_index != snap.correct_index
    ]
    record_mistakes(session, user_uuid, incorrect_question_ids)
    total_marks = Decimal(str(score["total_marks"]))
    max_marks = Decimal(str(score["max_marks"]))
    if max_marks > 0:
        percentage = (total_marks / max_marks * Decimal("100")).quantize(Decimal("0.01"))
    else:
        percentage = Decimal("0.00")
    if percentage < 0:
        percentage = Decimal("0.00")
    if percentage > 100:
        percentage = Decimal("100.00")
    started = session_row.server_started_at
    if started is not None:
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        time_taken = max(0, int((now - started).total_seconds()))
    else:
        time_taken = 0
    result = db.TestResult(
        session_id=session_row.id,
        user_id=user_uuid,
        total_questions=len(snapshots),
        correct_count=score["correct"],
        incorrect_count=score["incorrect"],
        unattempted_count=score["unattempted"],
        unknown_count=unknown_count,
        total_marks=total_marks,
        max_marks=max_marks,
        percentage=percentage,
        time_taken_seconds=time_taken,
        subject_breakdown=breakdowns["subject_breakdown"],
        topic_breakdown=breakdowns["topic_breakdown"],
        marking_config_id=marking.id,
        submitted_at=now,
    )
    session.add(result)
    session_row.status = "submitted"
    session_row.submitted_at = now
    try:
        session.commit()
    except IntegrityError:
        # A concurrent submit won the race — return its row.
        session.rollback()
        existing = _existing_result(session, session_row)
        if existing is None:
            raise
        return _result_to_dict(existing, session_row, marking)
    session.refresh(result)
    return _result_to_dict(result, session_row, marking)


# ---------------------------------------------------------------------------
# Result (stored row only — the full analytics UI is M8)
# ---------------------------------------------------------------------------


def get_result(session: Session, user: dict, test_id: str) -> dict:
    """The stored test_results row, or 404 when the test has not
    been submitted yet. No recomputation, no analytics here."""
    user_uuid = uuid.UUID(user["id"])
    session_row = _load_session_or_404(session, user_uuid, test_id)
    result = _existing_result(session, session_row)
    if result is None:
        raise _not_found("No result yet — submit the test first.")
    _, marking = _load_template_and_marking(session, session_row)
    return _result_to_dict(result, session_row, marking)
