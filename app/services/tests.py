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
import uuid
from decimal import Decimal

from sqlalchemy import exists
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models as db
from app.services.questions import _batch_answers, _batch_options, _correct_index, _parse_uuid
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


def _own_document_ids(session: Session, user_uuid: uuid.UUID, ids: list[str]) -> list[uuid.UUID]:
    out = []
    for raw in ids:
        doc_uuid = _parse_uuid(raw, "Document not found.")
        row = (
            session.query(db.Document)
            .filter(db.Document.id == doc_uuid)
            .filter(db.Document.user_id == user_uuid)
            .filter(db.Document.deleted_at.is_(None))
            .first()
        )
        if row is None:
            raise ApiError(status_code=404, code="not_found", message="Document not found.")
        out.append(doc_uuid)
    return out


def _existing_subject_ids(session: Session, ids: list[str]) -> list[uuid.UUID]:
    out = []
    for raw in ids:
        subject_uuid = _parse_uuid(raw, "Subject not found.")
        row = session.query(db.Subject).filter(db.Subject.id == subject_uuid).first()
        if row is None or not row.is_active:
            raise ApiError(status_code=404, code="not_found", message="Subject not found.")
        out.append(subject_uuid)
    return out


def _existing_topic_ids(session: Session, ids: list[str]) -> list[uuid.UUID]:
    out = []
    for raw in ids:
        topic_uuid = _parse_uuid(raw, "Topic not found.")
        row = session.query(db.Topic).filter(db.Topic.id == topic_uuid).first()
        if row is None:
            raise ApiError(status_code=404, code="not_found", message="Topic not found.")
        out.append(topic_uuid)
    return out


def _pool_rows(
    session: Session,
    user_uuid: uuid.UUID,
    source_type: str,
    source_ids: dict | list[str] | None,
) -> list[db.ExtractedQuestion]:
    """All of the user's extracted questions matching the source
    filter — before the unknown / no-option exclusions."""
    query = (
        session.query(db.ExtractedQuestion)
        .join(db.Document, db.Document.id == db.ExtractedQuestion.document_id)
        .filter(db.Document.user_id == user_uuid)
        .filter(db.Document.deleted_at.is_(None))
    )
    if source_type == "all":
        pass
    elif source_type == "documents":
        if not isinstance(source_ids, list) or not source_ids:
            raise _validation("source_ids must be a non-empty list of document ids.")
        query = query.filter(
            db.ExtractedQuestion.document_id.in_(_own_document_ids(session, user_uuid, source_ids))
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
        doc_uuids = _own_document_ids(session, user_uuid, doc_ids) if doc_ids else []
        subject_uuids = _existing_subject_ids(session, subject_ids) if subject_ids else []
        conditions = []
        if doc_uuids:
            conditions.append(db.ExtractedQuestion.document_id.in_(doc_uuids))
        if subject_uuids:
            conditions.append(
                exists().where(
                    (db.QuestionSubject.question_id == db.ExtractedQuestion.id)
                    & (db.QuestionSubject.subject_id.in_(subject_uuids))
                )
            )
        from sqlalchemy import or_ as _or

        query = query.filter(_or(*conditions))
    else:  # pragma: no cover - validated by the caller
        raise _validation(f"source_type must be one of: {', '.join(SOURCE_TYPES)}.")
    return query.all()


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


def _order_key(row: db.ExtractedQuestion) -> tuple[int, int, str]:
    number = (row.question_number or "").strip()
    if number.isdigit():
        return (0, int(number), str(row.document_id))
    return (1, 0, str(row.document_id))


def resolve_candidates(
    session: Session,
    user: dict,
    *,
    source_type: str,
    source_ids: dict | list[str] | None,
    include_unknown: bool,
) -> dict:
    """The selection pool for a source filter: candidates in a
    stable order (document, printed number) + exclusion counts.
    Explicit mode is resolved separately (see resolve_explicit)."""
    user_uuid = uuid.UUID(user["id"])
    rows = _pool_rows(session, user_uuid, source_type, source_ids)
    rows.sort(key=_order_key)
    classified = _classify_pool(session, rows, include_unknown)
    return classified


def resolve_explicit(
    session: Session,
    user: dict,
    question_ids: list[str],
    allow_repetition: bool,
    include_unknown: bool,
) -> dict:
    """Explicit question picks, in the order given. Every id must
    belong to the caller (404 otherwise). Duplicates are a 422
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
            .filter(db.Document.user_id == user_uuid)
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


def availability(
    session: Session,
    user: dict,
    *,
    source_type: str,
    source_ids: dict | list[str] | None,
    include_unknown: bool,
) -> dict:
    """How many questions a source filter can supply, before the
    user commits to building a test. The sample is the first 5
    candidates in printed-number order."""
    if source_type not in SOURCE_TYPES:
        raise _validation(f"source_type must be one of: {', '.join(SOURCE_TYPES)}.")
    if source_type == "explicit":
        raise _validation("availability does not apply to explicit picks — they are the list.")
    classified = resolve_candidates(
        session,
        user,
        source_type=source_type,
        source_ids=source_ids,
        include_unknown=include_unknown,
    )
    candidates = classified["candidates"]
    titles = {
        row.id: row.title
        for row in session.query(db.Document)
        .filter(db.Document.user_id == uuid.UUID(user["id"]))
        .filter(db.Document.deleted_at.is_(None))
        .all()
    }
    sample = []
    for row in candidates[:5]:
        sample.append(
            {
                "question_id": str(row.id),
                "document_id": str(row.document_id),
                "document_title": titles.get(row.document_id, ""),
                "number": row.question_number,
                "text": row.normalized_text,
                "correct_index": _correct_index(classified["answers"].get(row.id)),
            }
        )
    return {
        "available": len(candidates),
        "excluded_unknown": classified["excluded_unknown"],
        "excluded_no_options": classified["excluded_no_options"],
        "sample": sample,
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
        return {"document_ids": list(source_ids or [])}  # type: ignore[arg-type]
    if source_type == "subjects":
        return {"subject_ids": list(source_ids or [])}  # type: ignore[arg-type]
    if source_type == "topics":
        return {"topic_ids": list(source_ids or [])}  # type: ignore[arg-type]
    if source_type == "explicit":
        return {"question_ids": list(source_ids or [])}  # type: ignore[arg-type]
    if isinstance(source_ids, dict):
        return {
            "document_ids": list(source_ids.get("document_ids") or []),
            "subject_ids": list(source_ids.get("subject_ids") or []),
        }
    return None


# ---------------------------------------------------------------------------
# Test CRUD (template + session + snapshots, one transaction)
# ---------------------------------------------------------------------------


def _snapshot_dict(row: db.TestQuestionSnapshot) -> dict:
    return {
        "snapshot_id": str(row.id),
        "question_id": str(row.question_id) if row.question_id else None,
        "position": row.position,
        "question_text": row.question_text,
        "options": row.options,
        "correct_index": row.correct_index,
        "answer_source": row.answer_source,
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
            classified = resolve_candidates(
                session,
                user,
                source_type=source_type,
                source_ids=source_ids,
                include_unknown=include_unknown,
            )
            pool = classified["candidates"]
            if question_count > len(pool) and not allow_repetition:
                raise ApiError(
                    status_code=422,
                    code="insufficient_questions",
                    message=(
                        f"Only {len(pool)} question(s) are available from this "
                        f"source, but the test asks for {question_count}. "
                        f"({classified['excluded_unknown']} unknown and "
                        f"{classified['excluded_no_options']} no-option questions "
                        "were excluded.) Lower the count or widen the source."
                    ),
                )
            if not pool:
                raise ApiError(
                    status_code=422,
                    code="insufficient_questions",
                    message="No questions are available from this source.",
                )
            rng = random.Random(seed)
            if allow_repetition:
                picked = [rng.choice(pool) for _ in range(question_count)]
            else:
                picked = rng.sample(pool, question_count)
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
    detail["snapshots"] = [_snapshot_dict(row) for row in snapshots]
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
    detail["snapshots"] = [_snapshot_dict(row) for row in snapshots]
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
