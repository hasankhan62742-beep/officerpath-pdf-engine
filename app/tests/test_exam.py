# OfficerPath AI — Phase 2, M7
# Examination interface (GAP-6): start, session, answers, submit,
# result + Alembic 0007.
#
# Fixtures persist a real matched document through the Phase 1
# store (persist_matched_document) — the same rows the worker
# writes. The seed is 3 answered + 1 unknown, so every M7 rule
# (scoring, unknown exclusion, upsert, expiry) is exercised
# against real bank rows.

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.config import settings
from app.db import models as db
from app.pipeline.matching.models import MatchedDocument, ResolvedMCQ
from app.pipeline.matching.store import persist_matched_document
from app.tests.conftest import USER_A, auth_headers


def _matched() -> MatchedDocument:
    return MatchedDocument(
        questions=[
            ResolvedMCQ(
                number=1,
                text="What is the capital of Pakistan?",
                options=["Karachi", "Islamabad", "Lahore", "Quetta"],
                correct_index=1,
                answer_source="trailing-key",
                confidence=1.0,
                raw_confidence=1.0,
                verified=True,
                status="answered",
                page=1,
                paper="Paper 66",
            ),
            ResolvedMCQ(
                number=2,
                text="Which river flows through Multan?",
                options=["Indus", "Chenab", "Ravi", "Jhelum"],
                correct_index=0,
                answer_source="trailing-key",
                confidence=1.0,
                raw_confidence=1.0,
                verified=True,
                status="answered",
                page=1,
                paper="Paper 66",
            ),
            ResolvedMCQ(
                number=3,
                text="The largest desert of Pakistan is?",
                options=["Thar", "Cholistan", "Kharan", "Thal"],
                correct_index=2,
                answer_source="trailing-key",
                confidence=1.0,
                raw_confidence=1.0,
                verified=True,
                status="answered",
                page=2,
                paper="Paper 66",
            ),
            ResolvedMCQ(
                number=4,
                text="Which ocean is the largest?",
                options=["Atlantic", "Indian", "Pacific", "Arctic"],
                correct_index=-1,
                status="unknown",
                page=2,
                paper="Paper 66",
            ),
        ],
        qa_pairs=[],
        pending=[],
        counts={"questions": 4, "answered": 3, "unknown": 1, "pending": 0},
    )


@pytest.fixture()
def seeded_doc(engine_db):
    """One document owned by USER_A: 3 answered + 1 unknown.
    Returns (document_id, question_ids by number, snapshot
    correct_index by number)."""
    factory = engine_db
    session = factory()
    doc_id = uuid.uuid4()
    job_id = uuid.uuid4()
    session.add(
        db.Document(
            id=doc_id,
            user_id=uuid.UUID(USER_A),
            title="Model Paper 66",
            storage_path="inline-parse",
            file_type="pdf",
            file_size_bytes=1234,
            page_count=2,
            content_hash="b" * 64,
        )
    )
    session.add(db.Job(id=job_id, user_id=uuid.UUID(USER_A), document_id=doc_id, status="done"))
    session.commit()
    persist_matched_document(session, document_id=doc_id, job_id=job_id, matched=_matched())
    rows = (
        session.query(db.ExtractedQuestion).filter(db.ExtractedQuestion.document_id == doc_id).all()
    )
    by_number = {row.question_number: str(row.id) for row in rows}
    session.close()
    return doc_id, by_number


def _create(client, **overrides):
    payload = {
        "name": "M7 Exam 1",
        "question_count": 4,
        "source_type": "all",
        "include_unknown": True,
    }
    payload.update(overrides)
    return client.post("/api/v1/tests", json=payload, headers=auth_headers("token-user-a"))


def _create_test_id(client, **overrides) -> str:
    res = _create(client, **overrides)
    assert res.status_code == 201, res.text
    return res.json()["test_id"]


def _start(client, test_id, token="token-user-a"):
    return client.post(f"/api/v1/tests/{test_id}/start", headers=auth_headers(token))


def _session(client, test_id, token="token-user-a"):
    return client.get(f"/api/v1/tests/{test_id}/session", headers=auth_headers(token))


def _save(client, test_id, items, token="token-user-a"):
    return client.post(
        f"/api/v1/tests/{test_id}/answers",
        json={"answers": items},
        headers=auth_headers(token),
    )


def _submit(client, test_id, token="token-user-a"):
    return client.post(f"/api/v1/tests/{test_id}/submit", headers=auth_headers(token))


def _snapshots(client, test_id) -> list[dict]:
    res = _session(client, test_id)
    assert res.status_code == 200, res.text
    return res.json()["snapshots"]


def _backdate_start(factory, test_id: str, seconds_ago: int) -> None:
    """Harness-only clock move: push server_started_at into the
    past so expiry / remaining-time math is testable without
    waiting out a real time limit."""
    session = factory()
    row = session.query(db.TestSession).filter(db.TestSession.id == uuid.UUID(test_id)).first()
    assert row is not None
    row.server_started_at = datetime.now(UTC) - timedelta(seconds=seconds_ago)
    session.commit()
    session.close()


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------


def test_start_activates_and_second_start_is_409(client, engine_db, seeded_doc):
    test_id = _create_test_id(client)
    res = _start(client, test_id)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "in_progress"
    assert body["server_started_at"] is not None
    assert body["remaining_seconds"] is None  # untimed test: honest null
    assert body["expires_at"] is None
    # A second start is a conflict, not a silent re-start.
    res2 = _start(client, test_id)
    assert res2.status_code == 409
    assert res2.json()["error"]["code"] == "test_already_started"


def test_start_sets_expiry_from_time_limit(client, engine_db, seeded_doc):
    test_id = _create_test_id(client, time_limit_seconds=3600)
    res = _start(client, test_id)
    assert res.status_code == 200, res.text
    body = res.json()
    started = datetime.fromisoformat(body["server_started_at"])
    expires = datetime.fromisoformat(body["expires_at"])
    assert 3590 <= (expires - started).total_seconds() <= 3610
    assert 3590 <= body["remaining_seconds"] <= 3600


def test_start_is_per_user_and_requires_started_state(client, engine_db, seeded_doc):
    test_id = _create_test_id(client)
    assert _start(client, test_id, token="token-user-b").status_code == 404


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


def test_session_returns_snapshots_in_order_and_no_responses_yet(client, engine_db, seeded_doc):
    test_id = _create_test_id(client)
    _start(client, test_id)
    res = _session(client, test_id)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "in_progress"
    assert body["server_time"] is not None
    assert [s["position"] for s in body["snapshots"]] == [1, 2, 3, 4]
    # The random sample shuffles which question lands at which
    # position — the SET of frozen answers is what matters.
    assert sorted(s["correct_index"] for s in body["snapshots"]) == [-1, 0, 1, 2]
    assert body["responses"] == []


def test_remaining_seconds_counts_down_from_server_clock(client, engine_db, seeded_doc):
    test_id = _create_test_id(client, time_limit_seconds=3600)
    _start(client, test_id)
    _backdate_start(engine_db, test_id, seconds_ago=600)
    res = _session(client, test_id)
    assert res.status_code == 200, res.text
    remaining = res.json()["remaining_seconds"]
    assert 2990 <= remaining <= 3010, remaining


# ---------------------------------------------------------------------------
# Answers (upsert)
# ---------------------------------------------------------------------------


def test_save_answers_upsert_is_one_row(client, engine_db, seeded_doc):
    test_id = _create_test_id(client)
    _start(client, test_id)
    snaps = _snapshots(client, test_id)
    first = snaps[0]["snapshot_id"]
    res = _save(client, test_id, [{"snapshot_id": first, "selected_index": 1}])
    assert res.status_code == 200, res.text
    assert res.json()["saved"][0]["selected_index"] == 1
    # Saving again OVERWRITES the same row — never a second one.
    res = _save(client, test_id, [{"snapshot_id": first, "selected_index": 2}])
    assert res.status_code == 200, res.text
    assert res.json()["saved"][0]["selected_index"] == 2
    factory = engine_db
    session = factory()
    count = session.query(db.StudentResponse).count()
    session.close()
    assert count == 1


def test_save_answers_same_snapshot_twice_in_one_batch_is_one_row(client, engine_db, seeded_doc):
    # Regression (found by the M7 E2E): a batch naming the same snapshot
    # twice used to 500 with UNIQUE(session_id, snapshot_id), because
    # the second item queried before the first row was committed and
    # created a second pending row. Last item wins, exactly one row.
    test_id = _create_test_id(client)
    _start(client, test_id)
    snaps = _snapshots(client, test_id)
    first = snaps[0]["snapshot_id"]
    res = _save(
        client,
        test_id,
        [
            {"snapshot_id": first, "selected_index": 1},
            {"snapshot_id": first, "selected_index": 2, "marked_for_review": True},
        ],
    )
    assert res.status_code == 200, res.text
    saved = res.json()["saved"]
    assert len(saved) == 1
    assert saved[0]["selected_index"] == 2
    assert saved[0]["marked_for_review"] is True
    factory = engine_db
    session = factory()
    count = session.query(db.StudentResponse).count()
    session.close()
    assert count == 1


def test_save_answers_validates_option_range_and_snapshot(client, engine_db, seeded_doc):
    test_id = _create_test_id(client)
    _start(client, test_id)
    snaps = _snapshots(client, test_id)
    first = snaps[0]["snapshot_id"]
    # 4 options: valid indexes are 0-3.
    res = _save(client, test_id, [{"snapshot_id": first, "selected_index": 4}])
    assert res.status_code == 422
    # An unknown snapshot id is not in THIS test.
    res = _save(client, test_id, [{"snapshot_id": str(uuid.uuid4()), "selected_index": 0}])
    assert res.status_code == 404


def test_save_answers_requires_started_session(client, engine_db, seeded_doc):
    test_id = _create_test_id(client)
    snaps = client.get(f"/api/v1/tests/{test_id}", headers=auth_headers("token-user-a")).json()[
        "snapshots"
    ]
    res = _save(client, test_id, [{"snapshot_id": snaps[0]["snapshot_id"], "selected_index": 0}])
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "test_not_started"


def test_clear_response_keeps_row_with_null(client, engine_db, seeded_doc):
    test_id = _create_test_id(client)
    _start(client, test_id)
    snaps = _snapshots(client, test_id)
    first = snaps[0]["snapshot_id"]
    _save(client, test_id, [{"snapshot_id": first, "selected_index": 1}])
    res = _save(client, test_id, [{"snapshot_id": first, "selected_index": None}])
    assert res.status_code == 200, res.text
    assert res.json()["saved"][0]["selected_index"] is None
    factory = engine_db
    session = factory()
    row = session.query(db.StudentResponse).one()
    session.close()
    assert row.selected_index is None  # cleared, not deleted


def test_mark_for_review_toggle(client, engine_db, seeded_doc):
    test_id = _create_test_id(client)
    _start(client, test_id)
    snaps = _snapshots(client, test_id)
    first = snaps[0]["snapshot_id"]
    res = _save(
        client,
        test_id,
        [{"snapshot_id": first, "selected_index": 1, "marked_for_review": True}],
    )
    assert res.status_code == 200, res.text
    assert res.json()["saved"][0]["marked_for_review"] is True
    res = _session(client, test_id)
    assert res.json()["responses"][0]["marked_for_review"] is True


# ---------------------------------------------------------------------------
# Submit (hand-checked marking)
# ---------------------------------------------------------------------------


def test_submit_hand_checked_marks(client, engine_db, seeded_doc):
    """Snapshots: Q1 ci=1, Q2 ci=0, Q3 ci=2, Q4 UNKNOWN (-1).
    Answers: Q1 correct, Q2 incorrect, Q3 unattempted, Q4
    guessed (stored, never scored). PPSC default (+1/-0.25/0):
    total = 1 - 0.25 + 0 = 0.75; max = 3 scored x 1 = 3.0;
    percentage = 0.75/3.0 = 25.0; unknown_count = 1."""
    test_id = _create_test_id(client)
    _start(client, test_id)
    snaps = _snapshots(client, test_id)
    # The random sample shuffles positions, so identify
    # snapshots by their frozen correct_index (1, 0, 2, -1 —
    # all distinct in this seed).
    by_ci = {s["correct_index"]: s for s in snaps}
    res = _save(
        client,
        test_id,
        [
            {"snapshot_id": by_ci[1]["snapshot_id"], "selected_index": 1},  # correct
            {"snapshot_id": by_ci[0]["snapshot_id"], "selected_index": 3},  # incorrect
            {"snapshot_id": by_ci[-1]["snapshot_id"], "selected_index": 0},  # unknown
        ],
    )
    assert res.status_code == 200, res.text
    res = _submit(client, test_id)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total_questions"] == 4
    assert body["correct"] == 1
    assert body["incorrect"] == 1
    assert body["unattempted"] == 1
    assert body["unknown_count"] == 1
    assert body["total_marks"] == 0.75
    assert body["max_marks"] == 3.0
    assert body["percentage"] == 25.0
    assert body["time_taken_seconds"] >= 0
    assert body["status"] == "submitted"


def test_double_submit_is_idempotent_one_row(client, engine_db, seeded_doc):
    test_id = _create_test_id(client)
    _start(client, test_id)
    first = _submit(client, test_id)
    assert first.status_code == 200, first.text
    second = _submit(client, test_id)
    assert second.status_code == 200, second.text
    assert second.json()["result_id"] == first.json()["result_id"]
    assert second.json()["total_marks"] == first.json()["total_marks"]
    factory = engine_db
    session = factory()
    count = session.query(db.TestResult).count()
    session.close()
    assert count == 1


def test_result_before_submit_is_404_and_after_returns_stored_row(client, engine_db, seeded_doc):
    test_id = _create_test_id(client)
    _start(client, test_id)
    res = client.get(f"/api/v1/tests/{test_id}/result", headers=auth_headers("token-user-a"))
    assert res.status_code == 404
    submitted = _submit(client, test_id).json()
    res = client.get(f"/api/v1/tests/{test_id}/result", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    assert res.json()["result_id"] == submitted["result_id"]
    assert res.json()["total_marks"] == submitted["total_marks"]


def test_submit_unknown_only_never_scores_and_never_500(client, engine_db, seeded_doc):
    """A test of exactly one unknown question: no scored items,
    max_marks 0, percentage 0 — and no ValueError, no 500."""
    _, by_number = seeded_doc
    res = client.post(
        "/api/v1/tests",
        json={
            "name": "M7 Unknown only",
            "question_count": 1,
            "source_type": "explicit",
            "source_ids": [by_number["4"]],
            "include_unknown": True,
        },
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 201, res.text
    test_id = res.json()["test_id"]
    _start(client, test_id)
    res = _submit(client, test_id)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["correct"] == 0
    assert body["incorrect"] == 0
    assert body["unattempted"] == 0
    assert body["unknown_count"] == 1
    assert body["total_marks"] == 0.0
    assert body["max_marks"] == 0.0
    assert body["percentage"] == 0.0


def test_answers_after_submit_are_409(client, engine_db, seeded_doc):
    test_id = _create_test_id(client)
    _start(client, test_id)
    snaps = _snapshots(client, test_id)
    _submit(client, test_id)
    res = _save(client, test_id, [{"snapshot_id": snaps[0]["snapshot_id"], "selected_index": 0}])
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "test_already_submitted"


def test_exam_is_per_user(client, engine_db, seeded_doc):
    test_id = _create_test_id(client)
    assert _session(client, test_id, token="token-user-b").status_code == 404
    assert _start(client, test_id, token="token-user-b").status_code == 404
    assert _submit(client, test_id, token="token-user-b").status_code == 404


# ---------------------------------------------------------------------------
# Expiry (server clock only)
# ---------------------------------------------------------------------------


def test_expiry_blocks_save_stores_nothing_and_submit_still_works(client, engine_db, seeded_doc):
    test_id = _create_test_id(client, time_limit_seconds=60)
    _start(client, test_id)
    snaps = _snapshots(client, test_id)
    # Move the server anchor 120s into the past: the 60s limit
    # is long gone, but the browser never told the server that.
    _backdate_start(engine_db, test_id, seconds_ago=120)
    res = _save(client, test_id, [{"snapshot_id": snaps[0]["snapshot_id"], "selected_index": 1}])
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "time_expired"
    factory = engine_db
    session = factory()
    assert session.query(db.StudentResponse).count() == 0
    session.close()
    # The session now reads as expired with 0 remaining.
    res = _session(client, test_id)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "expired"
    assert res.json()["remaining_seconds"] == 0
    # Submitting after expiry still grades what WAS saved
    # (nothing here): 3 unattempted, 1 unknown, 0.0 marks.
    res = _submit(client, test_id)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["correct"] == 0
    assert body["incorrect"] == 0
    assert body["unattempted"] == 3
    assert body["unknown_count"] == 1
    assert body["total_marks"] == 0.0
    assert body["max_marks"] == 3.0


# ---------------------------------------------------------------------------
# Alembic 0007
# ---------------------------------------------------------------------------


def test_migration_0007_fresh_db_has_exam_tables(tmp_path, monkeypatch):
    """A database built ONLY by ``alembic upgrade head`` has the
    M7 tables, and a downgrade to 0006 drops them (clean DB)."""
    from alembic.config import Config

    from alembic import command

    db_file = tmp_path / "alembic-m7.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_file}")

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_file}")
    try:
        names = set(inspect(engine).get_table_names())
        assert "student_responses" in names
        assert "test_results" in names
    finally:
        engine.dispose()
    command.downgrade(cfg, "0006_m6_tests")
    engine = create_engine(f"sqlite:///{db_file}")
    try:
        names = set(inspect(engine).get_table_names())
        assert "student_responses" not in names
        assert "test_results" not in names
        assert "test_sessions" in names  # M6 tables untouched
    finally:
        engine.dispose()
    command.upgrade(cfg, "head")


def test_migration_0007_downgrade_refuses_with_exam_rows(tmp_path, monkeypatch):
    """Doc 03 §6: a downgrade never deletes user data silently."""
    from alembic.config import Config

    from alembic import command

    db_file = tmp_path / "alembic-m7-refuse.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_file}")

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{db_file}")
    try:
        with Session(engine) as session:
            config = session.query(db.MarkingConfig).first()
            template = db.TestTemplate(
                user_id=uuid.uuid4(),
                name="Refuse me",
                question_count=1,
                source_type="all",
                marking_config_id=config.id,
            )
            session.add(template)
            session.flush()
            test_session = db.TestSession(
                user_id=template.user_id,
                template_id=template.id,
                title="Refuse me",
                question_count=1,
                marking_config_id=config.id,
                status="submitted",
            )
            session.add(test_session)
            session.flush()
            result = db.TestResult(
                session_id=test_session.id,
                user_id=template.user_id,
                total_questions=1,
                correct_count=1,
                incorrect_count=0,
                unattempted_count=0,
                unknown_count=0,
                total_marks=1,
                max_marks=1,
                percentage=100,
                time_taken_seconds=30,
                marking_config_id=config.id,
                submitted_at=datetime.now(UTC),
            )
            session.add(result)
            session.commit()
        with pytest.raises(RuntimeError, match="Refusing downgrade"):
            command.downgrade(cfg, "0006_m6_tests")
    finally:
        engine.dispose()
