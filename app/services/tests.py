# OfficerPath AI — Phase 2, M6
# Test builder (GAP-5) + backend scoring.
#
# Ownership: every query filters by the JWT's user id; another
# user's test answers 404 (never leaks existence — the Phase 1
# pattern). All numbers come from real engine-DB rows.
#
# Hard rules enforced here (never in the frontend):
# - Snapshot rule: creating a test copies the question text,
#   options, correct answer and evidence state into
#   test_question_snapshots. A later bank edit, correction, or
#   deletion never changes a snapshot.
# - No duplicates in a test unless ``allow_repetition`` is
#   explicitly true (then the repetition is recorded on the
#   template). A duplicate in explicit mode is a 422, never
#   silently dropped.
# - Unknown answers (correct_index = -1) are EXCLUDED from the
#   candidate pool by default, and the counts excluded are
#   returned and stored. They enter a test only with
#   ``include_unknown`` — and then the snapshot still carries
#   correct_index = -1, so M7 must never score them.
# - Questions with no options (Q&A pairs) can never be scored
#   in a 4-option exam, so they are always excluded from the
#   pool (counted as excluded_no_options).
# - Marking is computed on the backend only (``score_answers``);
#   the frontend never supplies marks.
# - Availability: requesting more questions than the pool holds
#   is a 422 naming the available count — never a short test.

from __future__ import annotations

import random
import re
import uuid
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import Select, case, exists, func, or_
from sqlalchemy.orm import Query, Session

from app.core.errors import ApiError
from app.db import models as db
from app.services.questions import (
    _batch_answers,
    _batch_corrected,
    _batch_options,
    _batch_subjects,
    _correct_index,
    _latest_answer_label,
    _parse_uuid,
    _to_item,
    _valid_label_clause,
)
from app.utils.logging import get_logger

log = get_logger(__name__)

#: Question counts the UI offers as quick picks (doc 03 §2.4).
#: Any count 1–200 is accepted; the range is enforced here.
QUICK_COUNTS = (25, 50, 100, 150, 200)
MIN_QUESTION_COUNT = 1
MAX_QUESTION_COUNT = 200

SOURCE_TYPES = ("all", "documents", "subjects", "topics", "mixed", "explicit")
SESSION_STATUSES = ("created", "in_progress", "submitted", "abandoned", "expired")

#: Sane marking ranges (validated on every custom config).
MARKING_RANGES = {
    "correct_marks": (Decimal("0.25"), Decimal("10")),
    "incorrect_marks": (Decimal("-5"), Decimal("0")),
    "unattempted_marks": (Decimal("-1"), Decimal("0")),
}

PPSC_DEFAULT_NAME = "PPSC default"
PPSC_DEFAULT = {"correct_marks": 1.0, "incorrect_marks": -0.25, "unattempted_marks": 0.0}


def _not_found(what: str = "Test not found.") -> ApiError:
    return ApiError(status_code=404, code="not_found", message=what)


def _validation(message: str) -> ApiError:
    return ApiError(status_code=422, code="validation_error", message=message)


# ---------------------------------------------------------------------------
# Scoring (pure function — no DB). M7/M8 call this at submit time.
# ---------------------------------------------------------------------------


def score_answers(
    items: list[dict],
    *,
    correct_marks: float,
    incorrect_marks: float,
    unattempted_marks: float,
) -> dict:
    """Score one attempt from snapshots + selections.

    ``items`` is a list of ``{"correct_index": int,
    "selected_index": int | None}``. ``selected_index`` None means
    unattempted. An item with ``correct_index < 0`` (UNKNOWN) has
    no correct answer to score against — that is a caller bug
    (unknown questions must never reach scoring), so it raises
    ValueError instead of inventing a mark. Marks use Decimal
    arithmetic and are returned rounded to 2 decimal places.
    """
    correct = incorrect = unattempted = 0
    total = Decimal("0")
    cm = Decimal(str(correct_marks))
    im = Decimal(str(incorrect_marks))
    um = Decimal(str(unattempted_marks))
    for item in items:
        ci = item["correct_index"]
        if ci < 0:
            raise ValueError("Cannot score a question with an unknown answer (correct_index -1).")
        selected = item.get("selected_index")
        if selected is None:
            unattempted += 1
            total += um
        elif selected == ci:
            correct += 1
            total += cm
        else:
            incorrect += 1
            total += im
    total_questions = len(items)
    return {
        "total_questions": total_questions,
        "correct": correct,
        "incorrect": incorrect,
        "unattempted": unattempted,
        "total_marks": float(total.quantize(Decimal("0.01"))),
        "max_marks": float((cm * total_questions).quantize(Decimal("0.01"))),
    }


# ---------------------------------------------------------------------------
# Marking configs
# ---------------------------------------------------------------------------


def _validate_marking(values: dict) -> None:
    for field, (low, high) in MARKING_RANGES.items():
        raw = values.get(field)
        if raw is None:
            raise _validation(f"marking.{field} is required.")
        try:
            value = Decimal(str(raw))
        except Exception:
            raise _validation(f"marking.{field} must be a number.") from None
        if not (low <= value <= high):
            raise _validation(f"marking.{field} must be between {low} and {high} (got {raw}).")


def _default_marking_config(session: Session) -> db.MarkingConfig:
    """The PPSC default config — the seeded row when the database
    was migrated, created on the fly when it was built by
    ``create_all`` (tests) and the seed never ran."""
    config = session.query(db.MarkingConfig).filter(db.MarkingConfig.is_default.is_(True)).first()
    if config is not None:
        return config
    config = (
        session.query(db.MarkingConfig).filter(db.MarkingConfig.name == PPSC_DEFAULT_NAME).first()
    )
    if config is not None:
        return config
    config = db.MarkingConfig(name=PPSC_DEFAULT_NAME, is_default=True, **PPSC_DEFAULT)
    session.add(config)
    session.flush()
    return config


def list_marking_configs(session: Session) -> dict:
    # The default is seeded by Alembic 0006; a database built by
    # create_all (tests) never ran the seed, so ensure it here —
    # the list endpoint always shows at least the PPSC default.
    _default_marking_config(session)
    session.commit()
    rows = (
        session.query(db.MarkingConfig)
        .order_by(db.MarkingConfig.is_default.desc(), db.MarkingConfig.name)
        .all()
    )
    return {
        "marking_configs": [_marking_to_dict(row) for row in rows],
        "total": len(rows),
    }


def create_marking_config(session: Session, user: dict, payload: dict) -> dict:
    name = (payload.get("name") or "").strip()
    if not name:
        raise _validation("marking config name is required.")
    if len(name) > 200:
        raise _validation("marking config name must be at most 200 characters.")
    _validate_marking(payload)
    existing = session.query(db.MarkingConfig).filter(db.MarkingConfig.name == name).first()
    if existing is not None:
        raise ApiError(
            status_code=422,
            code="marking_name_taken",
            message=f"A marking config named {name!r} already exists.",
        )
    row = db.MarkingConfig(
        name=name,
        correct_marks=float(payload["correct_marks"]),
        incorrect_marks=float(payload["incorrect_marks"]),
        unattempted_marks=float(payload["unattempted_marks"]),
        is_default=False,
    )
    session.add(row)
    session.commit()
    return _marking_to_dict(row)


def _resolve_marking_config(
    session: Session, marking_config_id: str | None, marking: dict | None
) -> db.MarkingConfig:
    if marking is not None:
        name = (marking.get("name") or "").strip()
        if not name:
            raise _validation("Custom marking needs a name.")
        _validate_marking(marking)
        existing = session.query(db.MarkingConfig).filter(db.MarkingConfig.name == name).first()
        if existing is not None:
            raise ApiError(
                status_code=422,
                code="marking_name_taken",
                message=f"A marking config named {name!r} already exists.",
            )
        row = db.MarkingConfig(
            name=name,
            correct_marks=float(marking["correct_marks"]),
            incorrect_marks=float(marking["incorrect_marks"]),
            unattempted_marks=float(marking["unattempted_marks"]),
            is_default=False,
        )
        session.add(row)
        session.flush()
        return row
    if marking_config_id:
        row = (
            session.query(db.MarkingConfig)
            .filter(
                db.MarkingConfig.id == _parse_uuid(marking_config_id, "Marking config not found.")
            )
            .first()
        )
        if row is None:
            raise ApiError(status_code=404, code="not_found", message="Marking config not found.")
        return row
    return _default_marking_config(session)


def _marking_to_dict(row: db.MarkingConfig) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "correct_marks": row.correct_marks,
        "incorrect_marks": row.incorrect_marks,
        "unattempted_marks": row.unattempted_marks,
        "is_default": row.is_default,
    }


# ---------------------------------------------------------------------------
# Candidate resolution (the selection pool)
# ---------------------------------------------------------------------------


def _accessible_document_ids(
    session: Session, user_uuid: uuid.UUID, ids: list[str]
) -> list[uuid.UUID]:
    """Document ids the caller may build a test from: their own
    documents, or shared bank documents (M11). A private
    document of another student answers 404 — never leaks
    existence (the Phase 1 pattern). One query for the whole
    list, not one per id: the Read view passes hundreds of ids
    and the per-id loop was a round-trip per topic."""
    parsed = [_parse_uuid(raw, "Document not found.") for raw in ids]
    rows = (
        session.query(db.Document.id)
        .filter(db.Document.id.in_(parsed))
        .filter(
            or_(
                db.Document.user_id == user_uuid,
                db.Document.is_shared.is_(True),
            )
        )
        .filter(db.Document.deleted_at.is_(None))
        .all()
    )
    found = {row[0] for row in rows}
    for doc_uuid in parsed:
        if doc_uuid not in found:
            raise ApiError(status_code=404, code="not_found", message="Document not found.")
    return parsed


def _existing_subject_ids(session: Session, ids: list[str]) -> list[uuid.UUID]:
    """One query for the whole list (see _accessible_document_ids)."""
    parsed = [_parse_uuid(raw, "Subject not found.") for raw in ids]
    rows = (
        session.query(db.Subject.id)
        .filter(db.Subject.id.in_(parsed))
        .filter(db.Subject.is_active.is_(True))
        .all()
    )
    found = {row[0] for row in rows}
    for subject_uuid in parsed:
        if subject_uuid not in found:
            raise ApiError(status_code=404, code="not_found", message="Subject not found.")
    return parsed


def _existing_topic_ids(session: Session, ids: list[str]) -> list[uuid.UUID]:
    """One query for the whole list (see _accessible_document_ids).
    The Read view passes every topic of a subject (350 for
    Computer Science) — the per-id loop was 350 sequential
    round-trips before the availability query even started."""
    parsed = [_parse_uuid(raw, "Topic not found.") for raw in ids]
    rows = session.query(db.Topic.id).filter(db.Topic.id.in_(parsed)).all()
    found = {row[0] for row in rows}
    for topic_uuid in parsed:
        if topic_uuid not in found:
            raise ApiError(status_code=404, code="not_found", message="Topic not found.")
    return parsed


def _pool_query(
    session: Session,
    user_uuid: uuid.UUID,
    source_type: str,
    source_ids: dict | list[str] | None,
) -> Query:
    """Base query for the source filter — no rows loaded yet.
    The pool is the caller's own documents PLUS shared bank
    documents (M11); another student's private documents are
    never in it. Callers add classification, counts, or an
    ID-only select on top (see the performance note above
    _pool_counts)."""
    query = (
        session.query(db.ExtractedQuestion)
        .join(db.Document, db.Document.id == db.ExtractedQuestion.document_id)
        .filter(
            or_(
                db.Document.user_id == user_uuid,
                db.Document.is_shared.is_(True),
            )
        )
        .filter(db.Document.deleted_at.is_(None))
    )
    if source_type == "all":
        pass
    elif source_type == "documents":
        if not isinstance(source_ids, list) or not source_ids:
            raise _validation("source_ids must be a non-empty list of document ids.")
        query = query.filter(
            db.ExtractedQuestion.document_id.in_(
                _accessible_document_ids(session, user_uuid, source_ids)
            )
        )
    elif source_type == "subjects":
        if not isinstance(source_ids, list) or not source_ids:
            raise _validation("source_ids must be a non-empty list of subject ids.")
        subject_uuids = _existing_subject_ids(session, source_ids)
        query = query.filter(
            exists().where(
                (db.QuestionSubject.question_id == db.ExtractedQuestion.id)
                & (db.QuestionSubject.subject_id.in_(subject_uuids))
            )
        )
    elif source_type == "topics":
        if not isinstance(source_ids, list) or not source_ids:
            raise _validation("source_ids must be a non-empty list of topic ids.")
        topic_uuids = _existing_topic_ids(session, source_ids)
        query = query.filter(
            exists().where(
                (db.QuestionSubject.question_id == db.ExtractedQuestion.id)
                & (db.QuestionSubject.topic_id.in_(topic_uuids))
            )
        )
    elif source_type == "mixed":
        if not isinstance(source_ids, dict):
            raise _validation(
                "source_ids for mixed must be an object with document_ids and/or subject_ids."
            )
        doc_ids = source_ids.get("document_ids") or []
        subject_ids = source_ids.get("subject_ids") or []
        if not doc_ids and not subject_ids:
            raise _validation("mixed needs at least one document or subject id.")
        doc_uuids = _accessible_document_ids(session, user_uuid, doc_ids) if doc_ids else []
        subject_uuids = _existing_subject_ids(session, subject_ids) if subject_ids else []
        conditions: list[Any] = []
        if doc_uuids:
            conditions.append(db.ExtractedQuestion.document_id.in_(doc_uuids))
        if subject_uuids:
            conditions.append(
                exists().where(
                    (db.QuestionSubject.question_id == db.ExtractedQuestion.id)
                    & (db.QuestionSubject.subject_id.in_(subject_uuids))
                )
            )
        query = query.filter(or_(*conditions))
    else:  # pragma: no cover - validated by the caller
        raise _validation(f"source_type must be one of: {', '.join(SOURCE_TYPES)}.")
    return query


def _classify_pool(
    session: Session, rows: list[db.ExtractedQuestion], include_unknown: bool
) -> dict:
    """Split the pool into selectable candidates + exclusion
    counts. Unknown = no resolved answer (correct_index -1);
    no-option = Q&A pairs, which can never be scored."""
    ids = [row.id for row in rows]
    options = _batch_options(session, ids)
    answers = _batch_answers(session, ids)
    candidates: list[db.ExtractedQuestion] = []
    excluded_unknown = 0
    excluded_no_options = 0
    for row in rows:
        if not options.get(row.id):
            excluded_no_options += 1
            continue
        if _correct_index(answers.get(row.id)) < 0:
            excluded_unknown += 1
            if include_unknown:
                candidates.append(row)
            continue
        candidates.append(row)
    return {
        "candidates": candidates,
        "excluded_unknown": excluded_unknown,
        "excluded_no_options": excluded_no_options,
        "options": options,
        "answers": answers,
    }


def _topic_section_index(topic: db.Topic) -> int:
    """Section number of one topic, from its slug
    ("synonyms-s12") or its display name ("Synonyms —
    Section 12"). Topics without a section number sort
    first (index 0). The bank import names one topic per
    (subtopic, section) group, so this is what puts Section
    1's questions before Section 2's — printed numbers
    restart at 1 in every section, so the number alone
    cannot order a subtopic's questions."""
    slug = (topic.slug or "").strip()
    match = re.search(r"-s(\d+)$", slug)
    if match:
        return int(match.group(1))
    name = (topic.name or "").strip()
    match = re.search(r"—\s*Section\s+(\d+)\s*$", name)
    if match:
        return int(match.group(1))
    return 0


# ---------------------------------------------------------------------------
# Pool resolution without row materialisation (M12 performance fix).
#
# LIVE EVIDENCE (2026-11-24, Render logs): GET /tests/availability
# for source "all" took ~53s per call — the old code materialised
# all 52,573 ExtractedQuestion ORM objects, then every option and
# answer row, then sorted in Python. On Render free (512 MB,
# 0.1 CPU) that starved the 5s health check and the instance
# restarted mid-request, so the user's create-test POST never
# arrived.
#
# The pool is now resolved as plain tuples from four bounded
# queries — candidate columns, option holders, latest answer
# labels, topic assignments — and classified + sorted in Python
# with the exact same rules the old ORM code used. No per-row
# subqueries: question_options / extracted_answers carry no
# question_id index, so a correlated EXISTS / scalar subquery
# would scan those tables once per pool row (the first version
# of this fix did exactly that — 2s for 1,500 rows locally).
# No new indexes needed, same pool, same bank order, same
# exclusions, same messages.
# ---------------------------------------------------------------------------


def _label_is_known(label: str | None) -> bool:
    """The ``_correct_index(...) >= 0`` rule for one stored
    label: a single letter A-Z (case-insensitive, surrounding
    space ignored). No label, an empty label, or a non-letter
    label reads as unknown — the same as _correct_index,
    without its ord() crash on a multi-character label."""
    if not label:
        return False
    text = label.strip().upper()
    return len(text) == 1 and "A" <= text <= "Z"


def _bank_order_key(
    number: str | None, document_id: uuid.UUID, question_id: uuid.UUID, section_index: int = 0
) -> tuple[int, int, int, str, str]:
    """Bank order for one question: section first, then the
    printed number, then document, then id as a stable
    tiebreak. Printed numbers restart per section, so without
    the section index a subtopic's questions would interleave
    (Section 1 Q1, Section 2 Q1, Section 1 Q2, ...).
    ``section_index`` is 0 for pools without sections, which
    keeps the previous order exactly."""
    text = (number or "").strip()
    if text.isdigit():
        return (section_index, 0, int(text), str(document_id), str(question_id))
    return (section_index, 1, 0, str(document_id), str(question_id))


def _resolve_pool(
    session: Session,
    user_uuid: uuid.UUID,
    source_type: str,
    source_ids: dict | list[str] | None,
    include_unknown: bool,
) -> dict:
    """The selection pool for a source filter: bank-ordered
    candidate ids + exclusion counts + the per-question
    classification and topic assignments the by_topic
    breakdown needs. Four queries, no ORM rows:
    (1) candidate columns (id, printed number, document);
    (2) the questions holding at least one option;
    (3) every answer row, latest-by-created_at wins (the same
    rule _batch_answers uses);
    (4) topic assignments. Classification follows
    _classify_pool exactly: no options -> excluded_no_options
    (even when the answer is also unknown); options but no
    known answer -> excluded_unknown unless include_unknown;
    otherwise a candidate. Bank order is section, then printed
    number, then document, then id."""
    base = _pool_query(session, user_uuid, source_type, source_ids)
    # The pool ids as a SELECT, reused to restrict the three
    # classification queries to pool rows only. Query.statement
    # is a Select for a plain select query — the cast tells
    # mypy so (its declared type is a wider union).
    pool_ids = cast(Select, base.with_entities(db.ExtractedQuestion.id).statement)
    columns = base.with_entities(
        db.ExtractedQuestion.id,
        db.ExtractedQuestion.question_number,
        db.ExtractedQuestion.document_id,
    ).all()
    option_holders = {
        row[0]
        for row in session.query(db.QuestionOption.question_id)
        .filter(db.QuestionOption.question_id.in_(pool_ids))
        .distinct()
        .all()
    }
    answer_rows = (
        session.query(
            db.ExtractedAnswer.question_id,
            db.ExtractedAnswer.resolved_label,
            db.ExtractedAnswer.created_at,
        )
        .filter(db.ExtractedAnswer.question_id.in_(pool_ids))
        .order_by(db.ExtractedAnswer.created_at.desc())
        .all()
    )
    labels: dict[uuid.UUID, str | None] = {}
    for question_id, label, _created in answer_rows:
        labels.setdefault(question_id, label)
    topics = session.query(db.Topic).all()
    section_of = {topic.id: _topic_section_index(topic) for topic in topics}
    assignments = (
        session.query(db.QuestionSubject.question_id, db.QuestionSubject.topic_id)
        .filter(db.QuestionSubject.question_id.in_(pool_ids))
        .filter(db.QuestionSubject.topic_id.isnot(None))
        .all()
    )
    per_question_topics: dict[uuid.UUID, list[uuid.UUID]] = {}
    for question_id, topic_id in assignments:
        per_question_topics.setdefault(question_id, []).append(topic_id)
    classification: dict[uuid.UUID, str] = {}
    excluded_unknown = 0
    excluded_no_options = 0
    ordered: list[tuple[uuid.UUID, str | None, uuid.UUID, int]] = []
    for question_id, number, document_id in columns:
        if question_id not in option_holders:
            classification[question_id] = "no_options"
            excluded_no_options += 1
            continue
        if _label_is_known(labels.get(question_id)):
            classification[question_id] = "known"
        else:
            classification[question_id] = "unknown"
            excluded_unknown += 1
            if not include_unknown:
                continue
        topic_indexes = [
            section_of.get(topic_id, 0) for topic_id in per_question_topics.get(question_id, [])
        ]
        section_index = min(topic_indexes) if topic_indexes else 0
        ordered.append((question_id, number, document_id, section_index))
    ordered.sort(key=lambda c: _bank_order_key(c[1], c[2], c[0], c[3]))
    return {
        "candidate_ids": [c[0] for c in ordered],
        "excluded_unknown": excluded_unknown,
        "excluded_no_options": excluded_no_options,
        "classification": classification,
        "topics": per_question_topics,
    }


def resolve_explicit(
    session: Session,
    user: dict,
    question_ids: list[str],
    allow_repetition: bool,
    include_unknown: bool,
) -> dict:
    """Explicit question picks, in the order given. Every id must
    be the caller's own question or a shared-bank question
    (M11) — a private question of another student is a 404.
    Duplicates are a 422
    unless allow_repetition — then the repetition is the caller's
    explicit choice and is recorded on the template. An unknown
    pick (correct_index -1) is a 422 unless include_unknown —
    picking a question by id is not itself the unknown opt-in;
    the flag is."""
    if not question_ids:
        raise _validation("question_ids must be a non-empty list.")
    seen: set[str] = set()
    duplicates: list[str] = []
    for raw in question_ids:
        if raw in seen and raw not in duplicates:
            duplicates.append(raw)
        seen.add(raw)
    if duplicates and not allow_repetition:
        raise ApiError(
            status_code=422,
            code="duplicate_questions",
            message=(
                "Duplicate questions are not allowed in a test unless "
                f"allow_repetition is true: {len(duplicates)} duplicate id(s)."
            ),
        )
    user_uuid = uuid.UUID(user["id"])
    rows_by_id: dict[uuid.UUID, db.ExtractedQuestion] = {}
    for raw in seen:
        q_uuid = _parse_uuid(raw, "Question not found.")
        row = (
            session.query(db.ExtractedQuestion)
            .join(db.Document, db.Document.id == db.ExtractedQuestion.document_id)
            .filter(db.ExtractedQuestion.id == q_uuid)
            .filter(
                or_(
                    db.Document.user_id == user_uuid,
                    db.Document.is_shared.is_(True),
                )
            )
            .filter(db.Document.deleted_at.is_(None))
            .first()
        )
        if row is None:
            raise ApiError(status_code=404, code="not_found", message="Question not found.")
        rows_by_id[q_uuid] = row
    ordered = [rows_by_id[uuid.UUID(raw)] for raw in question_ids]
    classified = _classify_pool(session, ordered, include_unknown=True)
    # Explicit picks keep their given order (and repeats, when
    # allowed) — _classify_pool preserves input order.
    no_option = sum(1 for row in ordered if not classified["options"].get(row.id))
    if no_option:
        raise ApiError(
            status_code=422,
            code="validation_error",
            message=(
                f"{no_option} picked question(s) have no options (Q&A pairs) "
                "and cannot be scored in a test."
            ),
        )
    unknown_picks = sum(
        1 for row in ordered if _correct_index(classified["answers"].get(row.id)) < 0
    )
    if unknown_picks and not include_unknown:
        raise ApiError(
            status_code=422,
            code="validation_error",
            message=(
                f"{unknown_picks} picked question(s) have no known answer "
                "(correct_index -1). Set include_unknown to include them "
                "explicitly, flagged as unknown."
            ),
        )
    return classified


def _validate_range(start: int | None, end: int | None) -> tuple[int, int] | None:
    """A question range, validated as a pair: both or neither,
    integers, 1 <= start <= end. Returns None when no range
    was given (both None). The upper bound is checked against
    the live pool size by the caller — there is no fixed cap;
    the maximum is the section's own question count."""
    if start is None and end is None:
        return None
    if start is None or end is None:
        raise _validation("question_range_start and question_range_end must be given together.")
    if (
        not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
    ):
        raise _validation("question_range_start and question_range_end must be integers.")
    if start < 1 or end < start:
        raise _validation(
            "question_range_start must be at least 1 and no greater than "
            f"question_range_end (got {start}..{end})."
        )
    return (start, end)


def _require_single_topic_range(
    source_type: str, source_ids: dict | list[str] | None, question_range: tuple[int, int] | None
) -> None:
    """A range only makes sense over one section's bank-ordered
    pool: source_type "topics" with exactly one topic id."""
    if question_range is None:
        return
    if source_type != "topics" or not isinstance(source_ids, list) or len(source_ids) != 1:
        raise _validation(
            "A question range needs exactly one section (source_type "
            "'topics' with a single topic id)."
        )


def _apply_range(
    pool: list[db.ExtractedQuestion], start: int, end: int
) -> list[db.ExtractedQuestion]:
    """Slice a bank-ordered candidate pool to 1-based inclusive
    positions start..end. The end is validated against the live
    pool size, so the message always names the real count."""
    if end > len(pool):
        raise ApiError(
            status_code=422,
            code="insufficient_questions",
            message=(
                f"This section holds {len(pool)} question(s), but the "
                f"range asks for questions up to {end}. Lower the range end."
            ),
        )
    return pool[start - 1 : end]


def _topic_counts_sql(
    session: Session,
    user_uuid: uuid.UUID,
    topic_ids: list[str],
    include_unknown: bool,
) -> list[dict]:
    """Per-topic availability counts from ONE aggregate query —
    no pool resolution, no rows loaded. The Read view only
    needs these counts (it never shows the sample or the
    total), and resolving the whole subject pool for them took
    2.8s locally on a 33k-question subject (profiled
    2026-11-26) — 40s+ on the live 0.1-CPU box, past every
    proxy timeout, which is why the section counts never
    loaded. Classification follows ``_classify_pool`` exactly:
    no options -> excluded_no_options; options + latest answer
    a single letter A-Z -> available; options + no known answer
    -> available iff include_unknown else excluded_unknown.
    A question assigned to several requested topics counts
    under each; topics with no questions are included with
    zeros, so the UI can show every section tab."""
    topic_uuids = _existing_topic_ids(session, topic_ids)
    latest_answer = _latest_answer_label(session, topic_ids=topic_uuids)
    label_valid = _valid_label_clause(latest_answer.c.resolved_label)
    has_options = exists().where(db.QuestionOption.question_id == db.ExtractedQuestion.id)
    state = case(
        (~has_options, "no_options"),
        (label_valid, "known"),
        else_="unknown",
    )
    classified = (
        session.query(
            db.QuestionSubject.topic_id.label("topic_id"),
            db.ExtractedQuestion.id.label("question_id"),
            state.label("state"),
        )
        .join(
            db.ExtractedQuestion,
            db.ExtractedQuestion.id == db.QuestionSubject.question_id,
        )
        .join(db.Document, db.Document.id == db.ExtractedQuestion.document_id)
        .outerjoin(
            latest_answer,
            latest_answer.c.question_id == db.ExtractedQuestion.id,
        )
        .filter(db.QuestionSubject.topic_id.in_(topic_uuids))
        .filter(
            or_(
                db.Document.user_id == user_uuid,
                db.Document.is_shared.is_(True),
            )
        )
        .filter(db.Document.deleted_at.is_(None))
        .distinct()
        .subquery()
    )
    tallies = (
        session.query(
            classified.c.topic_id,
            func.sum(case((classified.c.state == "known", 1), else_=0)).label("known"),
            func.sum(case((classified.c.state == "unknown", 1), else_=0)).label("unknown"),
            func.sum(case((classified.c.state == "no_options", 1), else_=0)).label("no_options"),
        )
        .group_by(classified.c.topic_id)
        .all()
    )
    names = {
        topic.id: topic.name
        for topic in session.query(db.Topic).filter(db.Topic.id.in_(topic_uuids)).all()
    }
    by_id = {
        row[0]: {"known": row[1] or 0, "unknown": row[2] or 0, "no_options": row[3] or 0}
        for row in tallies
    }
    out = []
    for topic_id in topic_uuids:
        counts = by_id.get(topic_id, {"known": 0, "unknown": 0, "no_options": 0})
        unknown = counts["unknown"]
        out.append(
            {
                "topic_id": str(topic_id),
                "topic_name": names.get(topic_id, ""),
                "available": counts["known"] + (unknown if include_unknown else 0),
                "excluded_unknown": 0 if include_unknown else unknown,
                "excluded_no_options": counts["no_options"],
            }
        )
    return out


def _topic_breakdown(
    session: Session,
    topic_ids: list[str],
    include_unknown: bool,
    resolved: dict,
) -> list[dict]:
    """Per-topic counts for the requested topics, tallied from
    one resolved pool — no extra queries, no pool rows loaded.
    A question assigned to several topics counts under each.
    Topics with no questions are included with zeros, so the
    UI can show every section tab."""
    topic_uuids = _existing_topic_ids(session, topic_ids)
    topics = session.query(db.Topic).filter(db.Topic.id.in_(topic_uuids)).all()
    names = {topic.id: topic.name for topic in topics}
    classification: dict = resolved["classification"]
    per_question_topics: dict = resolved["topics"]
    tallies: dict[uuid.UUID, dict] = {
        topic_id: {"available": 0, "excluded_unknown": 0, "excluded_no_options": 0}
        for topic_id in topic_uuids
    }
    for question_id, state in classification.items():
        row_topics = [
            topic_id for topic_id in per_question_topics.get(question_id, []) if topic_id in tallies
        ]
        if not row_topics:
            continue
        if state == "no_options":
            for topic_id in row_topics:
                tallies[topic_id]["excluded_no_options"] += 1
        elif state == "unknown":
            for topic_id in row_topics:
                if include_unknown:
                    tallies[topic_id]["available"] += 1
                else:
                    tallies[topic_id]["excluded_unknown"] += 1
        else:  # known
            for topic_id in row_topics:
                tallies[topic_id]["available"] += 1
    return [
        {
            "topic_id": str(topic_id),
            "topic_name": names.get(topic_id, ""),
            "available": tallies[topic_id]["available"],
            "excluded_unknown": tallies[topic_id]["excluded_unknown"],
            "excluded_no_options": tallies[topic_id]["excluded_no_options"],
        }
        for topic_id in topic_uuids
    ]


def availability(
    session: Session,
    user: dict,
    *,
    source_type: str,
    source_ids: dict | list[str] | None,
    include_unknown: bool,
    question_range_start: int | None = None,
    question_range_end: int | None = None,
    counts_only: bool = False,
) -> dict:
    """How many questions a source filter can supply, before the
    user commits to building a test. The sample is the first 5
    candidates in bank order. With a range, the numbers describe
    the range slice only. ``by_topic`` (topics mode, no range)
    breaks the counts down per requested topic.

    ``counts_only`` (Read view): only the per-topic counts are
    needed, so the pool is never resolved — one aggregate query
    instead of loading tens of thousands of rows. Only valid
    for source_type "topics" with no range."""
    if source_type not in SOURCE_TYPES:
        raise _validation(f"source_type must be one of: {', '.join(SOURCE_TYPES)}.")
    if source_type == "explicit":
        raise _validation("availability does not apply to explicit picks — they are the list.")
    question_range = _validate_range(question_range_start, question_range_end)
    _require_single_topic_range(source_type, source_ids, question_range)
    user_uuid = uuid.UUID(user["id"])
    if counts_only:
        if source_type != "topics" or question_range is not None:
            raise _validation("counts_only needs source_type 'topics' with topic ids and no range.")
        if not isinstance(source_ids, list) or not source_ids:
            raise _validation("counts_only needs a non-empty list of topic ids.")
        by_topic = _topic_counts_sql(session, user_uuid, source_ids, include_unknown)
        return {
            "available": sum(row["available"] for row in by_topic),
            "excluded_unknown": sum(row["excluded_unknown"] for row in by_topic),
            "excluded_no_options": sum(row["excluded_no_options"] for row in by_topic),
            "sample": [],
            "by_topic": by_topic,
        }
    # One pool resolution (four small queries, no pool rows
    # loaded — the old path materialised the whole pool here
    # and took ~53s on the live 52,573-question bank). The
    # sample is the first 5 candidates in bank order.
    resolved = _resolve_pool(session, user_uuid, source_type, source_ids, include_unknown)
    ordered_ids = resolved["candidate_ids"]
    if question_range is not None:
        ordered_ids = _apply_range(ordered_ids, *question_range)
    sample_ids = ordered_ids[:5]
    sample_rows: list[db.ExtractedQuestion] = []
    answers_map: dict = {}
    titles: dict[uuid.UUID, str] = {}
    if sample_ids:
        loaded = (
            session.query(db.ExtractedQuestion)
            .filter(db.ExtractedQuestion.id.in_(sample_ids))
            .all()
        )
        by_id = {row.id: row for row in loaded}
        sample_rows = [by_id[sid] for sid in sample_ids]
        answers_map = _batch_answers(session, sample_ids)
        titles = {
            row.id: row.title
            for row in session.query(db.Document)
            .filter(db.Document.id.in_({row.document_id for row in sample_rows}))
            .all()
        }
    sample = []
    for row in sample_rows:
        sample.append(
            {
                "question_id": str(row.id),
                "document_id": str(row.document_id),
                "document_title": titles.get(row.document_id, ""),
                "number": row.question_number,
                "text": row.normalized_text,
                "correct_index": _correct_index(answers_map.get(row.id)),
            }
        )
    result: dict = {
        "available": len(ordered_ids),
        "excluded_unknown": resolved["excluded_unknown"],
        "excluded_no_options": resolved["excluded_no_options"],
        "sample": sample,
    }
    if source_type == "topics" and question_range is None and isinstance(source_ids, list):
        result["by_topic"] = _topic_breakdown(session, source_ids, include_unknown, resolved)
    return result


def list_section_questions(
    session: Session,
    user: dict,
    *,
    topic_ids: list[str],
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Reading mode (M12): one section's available questions in
    bank order, with options + the stored answer + the stored
    explanation. The pool is exactly the test pool for these
    topics (unknown and no-option questions excluded), so a
    reading range of 1..N maps exactly onto a test range of
    1..N. Shared bank sections are readable by every student;
    another student's private documents never appear."""
    if not topic_ids:
        raise _validation("topic_ids must be a non-empty list.")
    user_uuid = uuid.UUID(user["id"])
    # The page is sliced from one resolved pool — the old path
    # resolved (and classified) the whole section before
    # slicing. Full rows + options + answers load only for
    # this page.
    resolved = _resolve_pool(session, user_uuid, "topics", topic_ids, include_unknown=False)
    total = len(resolved["candidate_ids"])
    page_ids = resolved["candidate_ids"][offset : offset + limit]
    rows: list[db.ExtractedQuestion] = []
    if page_ids:
        loaded = (
            session.query(db.ExtractedQuestion).filter(db.ExtractedQuestion.id.in_(page_ids)).all()
        )
        by_id = {row.id: row for row in loaded}
        rows = [by_id[pid] for pid in page_ids]
    titles = {
        row.id: row.title
        for row in session.query(db.Document)
        .filter(db.Document.id.in_({row.document_id for row in rows}))
        .all()
    }
    ids = [row.id for row in rows]
    options = _batch_options(session, ids)
    answers = _batch_answers(session, ids)
    corrected = _batch_corrected(session, ids)
    subjects = _batch_subjects(session, ids)
    return {
        "questions": [
            _to_item(
                row,
                titles.get(row.document_id, ""),
                options.get(row.id, []),
                answers.get(row.id),
                row.id in corrected,
                subjects.get(row.id, []),
            )
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _normalize_source_ids(source_type: str, source_ids: dict | list[str] | None) -> dict | None:
    """Store source_ids in ONE shape (a dict) no matter the mode,
    so the API response type is stable: documents →
    {"document_ids": [...]}, subjects → {"subject_ids": [...]},
    topics → {"topic_ids": [...]}, mixed → as given, explicit →
    {"question_ids": [...]}, all → None."""
    if source_type == "all":
        return None
    if source_type == "documents":
        return {"document_ids": list(source_ids or [])}
    if source_type == "subjects":
        return {"subject_ids": list(source_ids or [])}
    if source_type == "topics":
        return {"topic_ids": list(source_ids or [])}
    if source_type == "explicit":
        return {"question_ids": list(source_ids or [])}
    if isinstance(source_ids, dict):
        return {
            "document_ids": list(source_ids.get("document_ids") or []),
            "subject_ids": list(source_ids.get("subject_ids") or []),
        }
    return None


# ---------------------------------------------------------------------------
# Test CRUD (template + session + snapshots, one transaction)
# ---------------------------------------------------------------------------


def _key_visible(status: str) -> bool:
    """The answer key is visible only once the attempt is over
    (status ``submitted``). A created or in-progress test — and
    an expired/abandoned one with no submission — must never
    expose it through the detail endpoints, or a student can
    read the key mid-test with a deliberate API call (the
    normal UI never calls the detail endpoint mid-test, but
    the API must not rely on that)."""
    return status == "submitted"


def _snapshot_dict(row: db.TestQuestionSnapshot, *, include_key: bool) -> dict:
    """One frozen snapshot. ``correct_index`` and
    ``answer_source`` are included ONLY when ``include_key``
    is True (the test is submitted and the owner is reviewing
    it). Otherwise both are None and only ``is_unknown`` is
    sent, mirroring the M9 exam-session shape, so the UI can
    still flag unknown questions without ever seeing the key.
    ``explanation`` follows the SAME rule (M10): it is the
    stored verbatim explanation, and it must never leak before
    submission — a pre-submit reader could otherwise read the
    reasoning for every answer. None means withheld, or no
    stored explanation at all."""
    return {
        "snapshot_id": str(row.id),
        "question_id": str(row.question_id) if row.question_id else None,
        "position": row.position,
        "question_text": row.question_text,
        "options": row.options,
        "correct_index": row.correct_index if include_key else None,
        "answer_source": row.answer_source if include_key else None,
        "explanation": row.explanation if include_key else None,
        "is_unknown": row.correct_index < 0,
        "source_document_id": str(row.source_document_id) if row.source_document_id else None,
        "source_page": row.source_page,
    }


def _test_to_dict(
    session_row: db.TestSession, template: db.TestTemplate, marking: db.MarkingConfig
) -> dict:
    return {
        "test_id": str(session_row.id),
        "template_id": str(template.id),
        "title": session_row.title,
        "description": template.description,
        "question_count": session_row.question_count,
        "source_type": template.source_type,
        "source_ids": template.source_ids,
        "allow_repetition": template.allow_repetition,
        "include_unknown": template.include_unknown,
        "status": session_row.status,
        "marking_config": _marking_to_dict(marking),
        "created_at": session_row.created_at.isoformat() if session_row.created_at else None,
        "updated_at": session_row.updated_at.isoformat() if session_row.updated_at else None,
    }


def _own_session(session: Session, user_uuid: uuid.UUID, test_id: uuid.UUID) -> db.TestSession:
    row = (
        session.query(db.TestSession)
        .filter(db.TestSession.id == test_id)
        .filter(db.TestSession.user_id == user_uuid)
        .first()
    )
    if row is None:
        raise _not_found()
    return row


def _load_template_and_marking(
    session: Session, session_row: db.TestSession
) -> tuple[db.TestTemplate, db.MarkingConfig]:
    template = None
    if session_row.template_id is not None:
        template = (
            session.query(db.TestTemplate)
            .filter(db.TestTemplate.id == session_row.template_id)
            .first()
        )
    if template is None:
        raise _not_found("Test template not found.")
    marking = (
        session.query(db.MarkingConfig)
        .filter(db.MarkingConfig.id == session_row.marking_config_id)
        .first()
    )
    if marking is None:
        raise _not_found("Marking config not found.")
    return template, marking


def create_test(session: Session, user: dict, payload: dict) -> dict:
    """Build a test: template + session + frozen snapshots, one
    transaction. Nothing is committed until every snapshot is
    written — no partial test ever exists."""
    name = (payload.get("name") or "").strip()
    if not name:
        raise _validation("Test name is required.")
    if len(name) > 200:
        raise _validation("Test name must be at most 200 characters.")
    description = (payload.get("description") or "").strip() or None
    if description is not None and len(description) > 2000:
        raise _validation("Description must be at most 2000 characters.")
    question_count = payload.get("question_count")
    if not isinstance(question_count, int) or isinstance(question_count, bool):
        raise _validation("question_count must be an integer.")
    if not (MIN_QUESTION_COUNT <= question_count <= MAX_QUESTION_COUNT):
        raise _validation(
            f"question_count must be between {MIN_QUESTION_COUNT} and {MAX_QUESTION_COUNT}."
        )
    source_type = payload.get("source_type")
    if source_type not in SOURCE_TYPES:
        raise _validation(f"source_type must be one of: {', '.join(SOURCE_TYPES)}.")
    source_ids = payload.get("source_ids")
    allow_repetition = bool(payload.get("allow_repetition", False))
    include_unknown = bool(payload.get("include_unknown", False))
    time_limit = payload.get("time_limit_seconds")
    if time_limit is not None and (
        not isinstance(time_limit, int)
        or isinstance(time_limit, bool)
        or not (60 <= time_limit <= 86400)
    ):
        raise _validation("time_limit_seconds must be between 60 and 86400 when set.")
    seed = random.SystemRandom().randint(0, 2**31 - 1)
    # M12 — a range needs source_type "topics" (any other source
    # has no single section whose bank order the positions refer
    # to). Validated up front so explicit mode + range is a 422
    # before any pool work happens.
    question_range = _validate_range(
        payload.get("question_range_start"), payload.get("question_range_end")
    )
    if question_range is not None and source_type != "topics":
        raise _validation("A question range needs source_type 'topics'.")

    try:
        marking = _resolve_marking_config(
            session, payload.get("marking_config_id"), payload.get("marking")
        )
        if source_type == "explicit":
            if not isinstance(source_ids, list):
                raise _validation("source_ids must be a list of question ids for explicit mode.")
            classified = resolve_explicit(
                session, user, source_ids, allow_repetition, include_unknown
            )
            picked = classified["candidates"]
            if len(picked) != question_count:
                raise ApiError(
                    status_code=422,
                    code="insufficient_questions",
                    message=(
                        f"Explicit mode picked {len(picked)} question(s) but "
                        f"question_count is {question_count} — they must match."
                    ),
                )
        else:
            # ID-only pick: one pool resolution, then full rows
            # + options + answers ONLY for the picked questions.
            # The old path materialised the whole pool here
            # (~53s live). rng.sample/choice pick by index, so
            # the same seed over the same bank-ordered ids picks
            # the same questions as before.
            user_uuid = uuid.UUID(user["id"])
            resolved = _resolve_pool(session, user_uuid, source_type, source_ids, include_unknown)
            pool_ids = resolved["candidate_ids"]
            if question_range is not None:
                _require_single_topic_range(source_type, source_ids, question_range)
                pool_ids = _apply_range(pool_ids, *question_range)
            if question_count > len(pool_ids) and not allow_repetition:
                range_note = (
                    f" (questions {question_range[0]}..{question_range[1]} of this section)"
                    if question_range is not None
                    else ""
                )
                raise ApiError(
                    status_code=422,
                    code="insufficient_questions",
                    message=(
                        f"Only {len(pool_ids)} question(s) are available from this "
                        f"source{range_note}, but the test asks for {question_count}. "
                        f"({resolved['excluded_unknown']} unknown and "
                        f"{resolved['excluded_no_options']} no-option questions "
                        "were excluded.) Lower the count or widen the source."
                    ),
                )
            if not pool_ids:
                raise ApiError(
                    status_code=422,
                    code="insufficient_questions",
                    message="No questions are available from this source.",
                )
            rng = random.Random(seed)
            if allow_repetition:
                picked_ids = [rng.choice(pool_ids) for _ in range(question_count)]
            else:
                picked_ids = rng.sample(pool_ids, question_count)
            loaded = (
                session.query(db.ExtractedQuestion)
                .filter(db.ExtractedQuestion.id.in_(set(picked_ids)))
                .all()
            )
            by_id = {row.id: row for row in loaded}
            picked = [by_id[pid] for pid in picked_ids]
            options_map = _batch_options(session, list(set(picked_ids)))
            answers_map = _batch_answers(session, list(set(picked_ids)))
            classified = {
                "options": options_map,
                "answers": answers_map,
                "excluded_unknown": resolved["excluded_unknown"],
                "excluded_no_options": resolved["excluded_no_options"],
            }
        options_map = classified["options"]
        answers_map = classified["answers"]
        user_uuid = uuid.UUID(user["id"])
        template = db.TestTemplate(
            user_id=user_uuid,
            name=name,
            description=description,
            question_count=question_count,
            source_type=source_type,
            source_ids=_normalize_source_ids(source_type, source_ids),
            allow_repetition=allow_repetition,
            include_unknown=include_unknown,
            selection_seed=seed if source_type != "explicit" else None,
            excluded_unknown=classified["excluded_unknown"],
            excluded_no_options=classified["excluded_no_options"],
            marking_config_id=marking.id,
        )
        session.add(template)
        session.flush()
        session_row = db.TestSession(
            user_id=user_uuid,
            template_id=template.id,
            title=name,
            question_count=question_count,
            marking_config_id=marking.id,
            status="created",
            time_limit_seconds=time_limit,
        )
        session.add(session_row)
        session.flush()
        for position, question in enumerate(picked, start=1):
            answer = answers_map.get(question.id)
            option_texts = options_map.get(question.id, [])
            session.add(
                db.TestQuestionSnapshot(
                    session_id=session_row.id,
                    question_id=question.id,
                    position=position,
                    question_text=question.normalized_text,
                    options=[
                        {"label": chr(65 + i), "text": text} for i, text in enumerate(option_texts)
                    ],
                    correct_index=_correct_index(answer),
                    answer_source=(answer.resolution_method or "") if answer else "",
                    # Frozen copy of the bank explanation (M10): a
                    # past test keeps its explanation even if the
                    # bank question is later edited. None when the
                    # bank holds none — never invented.
                    explanation=question.explanation,
                    source_document_id=question.document_id,
                    source_page=(question.source_pages or [None])[0],
                )
            )
        session.commit()
    except ApiError:
        session.rollback()
        raise
    snapshots = (
        session.query(db.TestQuestionSnapshot)
        .filter(db.TestQuestionSnapshot.session_id == session_row.id)
        .order_by(db.TestQuestionSnapshot.position)
        .all()
    )
    detail = _test_to_dict(session_row, template, marking)
    detail["snapshots"] = [_snapshot_dict(row, include_key=False) for row in snapshots]
    detail["excluded_unknown"] = template.excluded_unknown
    detail["excluded_no_options"] = template.excluded_no_options
    return detail


def list_tests(session: Session, user: dict, *, limit: int = 20, offset: int = 0) -> dict:
    user_uuid = uuid.UUID(user["id"])
    query = (
        session.query(db.TestSession)
        .filter(db.TestSession.user_id == user_uuid)
        .order_by(db.TestSession.created_at.desc())
    )
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    items = []
    for row in rows:
        template, marking = _load_template_and_marking(session, row)
        items.append(_test_to_dict(row, template, marking))
    return {"tests": items, "total": total, "limit": limit, "offset": offset}


def get_test(session: Session, user: dict, test_id: str) -> dict:
    user_uuid = uuid.UUID(user["id"])
    session_row = _own_session(session, user_uuid, _parse_uuid(test_id))
    template, marking = _load_template_and_marking(session, session_row)
    snapshots = (
        session.query(db.TestQuestionSnapshot)
        .filter(db.TestQuestionSnapshot.session_id == session_row.id)
        .order_by(db.TestQuestionSnapshot.position)
        .all()
    )
    detail = _test_to_dict(session_row, template, marking)
    detail["snapshots"] = [
        _snapshot_dict(row, include_key=_key_visible(session_row.status)) for row in snapshots
    ]
    detail["excluded_unknown"] = template.excluded_unknown
    detail["excluded_no_options"] = template.excluded_no_options
    return detail


def update_test(session: Session, user: dict, test_id: str, payload: dict) -> dict:
    user_uuid = uuid.UUID(user["id"])
    session_row = _own_session(session, user_uuid, _parse_uuid(test_id))
    if session_row.status != "created":
        raise ApiError(
            status_code=409,
            code="test_already_started",
            message=f"A test in status {session_row.status!r} can no longer be edited.",
        )
    template, marking = _load_template_and_marking(session, session_row)
    name = payload.get("name")
    if name is not None:
        name = name.strip()
        if not name:
            raise _validation("Test name must not be empty.")
        if len(name) > 200:
            raise _validation("Test name must be at most 200 characters.")
        template.name = name
        session_row.title = name
    if "description" in payload:
        description = (payload.get("description") or "").strip() or None
        if description is not None and len(description) > 2000:
            raise _validation("Description must be at most 2000 characters.")
        template.description = description
    session.commit()
    return _test_to_dict(session_row, template, marking)


def delete_test(session: Session, user: dict, test_id: str) -> dict:
    user_uuid = uuid.UUID(user["id"])
    session_row = _own_session(session, user_uuid, _parse_uuid(test_id))
    if session_row.status != "created":
        raise ApiError(
            status_code=409,
            code="test_already_started",
            message=(
                f"A test in status {session_row.status!r} cannot be deleted — "
                "it already has an attempt. Delete is only allowed before "
                "any attempt exists."
            ),
        )
    template_id = session_row.template_id
    session.delete(session_row)  # snapshots cascade
    if template_id is not None:
        template = session.query(db.TestTemplate).filter(db.TestTemplate.id == template_id).first()
        if template is not None:
            session.delete(template)
    session.commit()
    return {"test_id": str(session_row.id), "deleted": True}
