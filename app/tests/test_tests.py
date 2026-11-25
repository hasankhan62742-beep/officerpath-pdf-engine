# OfficerPath AI — Phase 2, M6
# Test builder (GAP-5) + backend scoring + Alembic 0006.
#
# Fixtures persist a real matched document through the Phase 1
# store (persist_matched_document) — the same rows the worker
# writes — then exercise the new test APIs against them. The
# seed is the M5 shape: 2 answered (1 inferred), 1 unknown,
# 1 pending, 1 qa_pair counted only.

import uuid

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.config import settings
from app.db import models as db
from app.pipeline.matching.models import MatchedDocument, ResolvedMCQ
from app.pipeline.matching.store import persist_matched_document
from app.services import tests as test_service
from app.tests.conftest import USER_A, auth_headers

DOC_TITLE = "Model Paper 66"


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
                evidences=[
                    {
                        "detector": "trailing-key",
                        "question_number": 1,
                        "correct_index": 1,
                        "correct_letter": "B",
                        "confidence": 1.0,
                        "evidence": "key entry 1 -> (B)",
                        "answer_text": None,
                        "detail": {},
                    }
                ],
            ),
            ResolvedMCQ(
                number=2,
                text="Which river flows through Multan?",
                options=["Indus", "Chenab", "Ravi", "Jhelum"],
                correct_index=-1,
                status="unknown",
                page=1,
                paper="Paper 66",
            ),
            ResolvedMCQ(
                number=4,
                text="The largest desert of Pakistan is?",
                options=["Thar", "Cholistan", "Kharan", "Thal"],
                correct_index=0,
                answer_source="inferred",
                confidence=0.62,
                raw_confidence=0.62,
                inferred=True,
                status="answered",
                page=2,
                paper="Paper 66",
                evidences=[
                    {
                        "detector": "style",
                        "question_number": 4,
                        "correct_index": 0,
                        "correct_letter": "A",
                        "confidence": 0.62,
                        "evidence": "bold option A",
                        "answer_text": None,
                        "detail": {},
                    }
                ],
            ),
        ],
        qa_pairs=[
            ResolvedMCQ(
                number=None,
                text="What is AI?",
                options=[],
                kind="qa_pair",
                answer_text="Artificial Intelligence",
                status="answered",
            )
        ],
        pending=[
            {
                "number": 3,
                "text": "Who wrote the national anthem?",
                "options": ["Hafeez Jalandhari", "Iqbal", "Faiz", "Ghalib"],
                "reason": "no-key-entry",
                "page": 1,
                "paper": "Paper 66",
            }
        ],
        counts={"questions": 3, "answered": 2, "unknown": 1, "pending": 1},
    )


@pytest.fixture()
def seeded_doc(engine_db):
    """One document owned by USER_A with a persisted matched
    result (2 answered incl. 1 inferred, 1 unknown, 1 pending,
    1 qa_pair counted only). Returns (document_id, question_ids
    by number)."""
    factory = engine_db
    session = factory()
    doc_id = uuid.uuid4()
    job_id = uuid.uuid4()
    session.add(
        db.Document(
            id=doc_id,
            user_id=uuid.UUID(USER_A),
            title=DOC_TITLE,
            storage_path="inline-parse",
            file_type="pdf",
            file_size_bytes=1234,
            page_count=2,
            content_hash="a" * 64,
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


def _create_payload(**overrides):
    payload = {
        "name": "PPSC Practice 1",
        "question_count": 2,
        "source_type": "all",
    }
    payload.update(overrides)
    return payload


def _create(client, payload):
    return client.post("/api/v1/tests", json=payload, headers=auth_headers("token-user-a"))


# ---------------------------------------------------------------------------
# Scoring (pure function — the backend calculation M7/M8 will use)
# ---------------------------------------------------------------------------


def test_scoring_worked_example_ppsc_default():
    """The brief's worked example: 10 correct, 2 incorrect, 3
    unattempted with +1 / −0.25 / 0 = 10 − 0.5 + 0 = 9.5."""
    items = (
        [{"correct_index": 0, "selected_index": 0}] * 10
        + [{"correct_index": 0, "selected_index": 1}] * 2
        + [{"correct_index": 0, "selected_index": None}] * 3
    )
    result = test_service.score_answers(
        items, correct_marks=1.0, incorrect_marks=-0.25, unattempted_marks=0.0
    )
    assert result == {
        "total_questions": 15,
        "correct": 10,
        "incorrect": 2,
        "unattempted": 3,
        "total_marks": 9.5,
        "max_marks": 15.0,
    }


def test_scoring_custom_marking_and_all_unattempted():
    items = [
        {"correct_index": 2, "selected_index": 2},
        {"correct_index": 2, "selected_index": 2},
        {"correct_index": 2, "selected_index": 2},
        {"correct_index": 1, "selected_index": 0},
        {"correct_index": 1, "selected_index": None},
    ]
    result = test_service.score_answers(
        items, correct_marks=2.0, incorrect_marks=-0.5, unattempted_marks=0.0
    )
    assert result["correct"] == 3
    assert result["incorrect"] == 1
    assert result["unattempted"] == 1
    assert result["total_marks"] == 5.5  # 3*2 − 0.5
    assert result["max_marks"] == 10.0
    empty = test_service.score_answers(
        [], correct_marks=1.0, incorrect_marks=-0.25, unattempted_marks=0.0
    )
    assert empty["total_marks"] == 0.0
    assert empty["max_marks"] == 0.0


def test_scoring_unknown_question_raises():
    with pytest.raises(ValueError, match="unknown answer"):
        test_service.score_answers(
            [{"correct_index": -1, "selected_index": 0}],
            correct_marks=1.0,
            incorrect_marks=-0.25,
            unattempted_marks=0.0,
        )


# ---------------------------------------------------------------------------
# Marking configs
# ---------------------------------------------------------------------------


def test_marking_configs_default_and_validation(client, engine_db):
    res = client.get("/api/v1/marking-configs", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 1  # the PPSC default, created on the fly
    default = body["marking_configs"][0]
    assert default["name"] == "PPSC default"
    assert default["correct_marks"] == 1.0
    assert default["incorrect_marks"] == -0.25
    assert default["unattempted_marks"] == 0.0
    assert default["is_default"] is True
    # Invalid ranges are 422s, never stored.
    res = client.post(
        "/api/v1/marking-configs",
        json={
            "name": "Bad",
            "correct_marks": 1.0,
            "incorrect_marks": 0.5,
            "unattempted_marks": 0.0,
        },
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 422
    res = client.post(
        "/api/v1/marking-configs",
        json={
            "name": "Bad",
            "correct_marks": 0.0,
            "incorrect_marks": -0.25,
            "unattempted_marks": 0.0,
        },
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 422
    # A valid custom config stores and re-lists.
    res = client.post(
        "/api/v1/marking-configs",
        json={
            "name": "No negative",
            "correct_marks": 1.0,
            "incorrect_marks": 0.0,
            "unattempted_marks": 0.0,
        },
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "No negative"
    # Same name twice is a 422.
    res = client.post(
        "/api/v1/marking-configs",
        json={
            "name": "No negative",
            "correct_marks": 1.0,
            "incorrect_marks": 0.0,
            "unattempted_marks": 0.0,
        },
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Availability + creation
# ---------------------------------------------------------------------------


def test_availability_excludes_unknown_and_counts_them(client, engine_db, seeded_doc):
    res = client.get(
        "/api/v1/tests/availability?source_type=all", headers=auth_headers("token-user-a")
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["available"] == 2  # Q1 + Q4 (answered); Q2 + Q3 unknown
    assert body["excluded_unknown"] == 2
    assert body["excluded_no_options"] == 0  # qa_pair is a count, not a row
    assert len(body["sample"]) == 2
    res = client.get(
        "/api/v1/tests/availability?source_type=all&include_unknown=true",
        headers=auth_headers("token-user-a"),
    )
    assert res.json()["available"] == 4
    assert res.json()["excluded_unknown"] == 2  # still reported, now included
    res = client.get(
        "/api/v1/tests/availability?source_type=bogus", headers=auth_headers("token-user-a")
    )
    assert res.status_code == 422


def test_availability_counts_only_matches_full_counts(client, engine_db, seeded_doc):
    """Read view (bug a): ``counts_only`` must return exactly
    the same per-topic counts as the full pool resolution — it
    is only a faster path to the same numbers, never a different
    classification. The sample is empty: the Read view never
    shows it."""
    _, by_number = seeded_doc
    factory = engine_db
    session = factory()
    subject_id = uuid.uuid4()
    topic_id = uuid.uuid4()
    session.add(db.Subject(id=subject_id, name="General Knowledge", slug="general-knowledge"))
    session.add(
        db.Topic(id=topic_id, subject_id=subject_id, name="Section One", slug="section-one")
    )
    for qid in by_number.values():
        session.add(
            db.QuestionSubject(
                question_id=uuid.UUID(qid),
                subject_id=subject_id,
                topic_id=topic_id,
                assigned_by=uuid.UUID(USER_A),
            )
        )
    session.commit()
    session.close()

    base = f"/api/v1/tests/availability?source_type=topics&topic_ids={topic_id}"
    full = client.get(base, headers=auth_headers("token-user-a"))
    assert full.status_code == 200, full.text
    fast = client.get(f"{base}&counts_only=true", headers=auth_headers("token-user-a"))
    assert fast.status_code == 200, fast.text
    assert fast.json()["sample"] == []
    for key in ("available", "excluded_unknown", "excluded_no_options", "by_topic"):
        assert fast.json()[key] == full.json()[key], key
    assert fast.json()["available"] == 2  # Q1 + Q4 (answered); Q2 + Q3 unknown
    assert fast.json()["excluded_unknown"] == 2
    assert fast.json()["by_topic"][0]["topic_name"] == "Section One"

    # counts_only needs topics mode with no range — anything else is a 422.
    res = client.get(
        "/api/v1/tests/availability?source_type=all&counts_only=true",
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 422
    res = client.get(
        f"{base}&counts_only=true&question_range_start=1&question_range_end=2",
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 422


def test_create_test_from_all_freezes_ppsc_default(client, engine_db, seeded_doc):
    res = _create(client, _create_payload())
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["title"] == "PPSC Practice 1"
    assert body["question_count"] == 2
    assert body["status"] == "created"
    assert body["marking_config"]["name"] == "PPSC default"
    assert body["marking_config"]["correct_marks"] == 1.0
    assert body["marking_config"]["incorrect_marks"] == -0.25
    assert body["excluded_unknown"] == 2
    assert body["excluded_no_options"] == 0
    assert len(body["snapshots"]) == 2
    positions = [s["position"] for s in body["snapshots"]]
    assert positions == [1, 2]
    for snap in body["snapshots"]:
        assert snap["is_unknown"] is False  # no unknown slipped in
        assert snap["correct_index"] is None  # key withheld until submit
        assert len(snap["options"]) == 4
        assert snap["options"][0]["label"] == "A"
        assert snap["question_text"]
    # The list shows it, with the marking summary.
    res = client.get("/api/v1/tests", headers=auth_headers("token-user-a"))
    assert res.json()["total"] == 1
    assert res.json()["tests"][0]["test_id"] == body["test_id"]


def test_create_test_insufficient_questions_names_the_limit(client, engine_db, seeded_doc):
    res = _create(client, _create_payload(question_count=100))
    assert res.status_code == 422, res.text
    message = res.json()["error"]["message"]
    assert "Only 2 question(s) are available" in message
    assert "100" in message
    # No partial test was created.
    res = client.get("/api/v1/tests", headers=auth_headers("token-user-a"))
    assert res.json()["total"] == 0


def test_create_test_include_unknown_flags_snapshots(client, engine_db, seeded_doc):
    res = _create(client, _create_payload(question_count=4, include_unknown=True))
    assert res.status_code == 201, res.text
    body = res.json()
    assert len(body["snapshots"]) == 4
    unknowns = [s for s in body["snapshots"] if s["is_unknown"]]
    assert len(unknowns) == 2  # Q2 + Q3, flagged by is_unknown itself
    assert all(s["correct_index"] is None for s in body["snapshots"])  # key withheld
    for snap in unknowns:
        assert snap["options"]  # options are still frozen for review


def test_create_test_validates_count_and_name(client, engine_db, seeded_doc):
    assert _create(client, _create_payload(question_count=0)).status_code == 422
    assert _create(client, _create_payload(question_count=201)).status_code == 422
    assert _create(client, _create_payload(name="   ")).status_code == 422
    assert _create(client, _create_payload(source_type="bogus")).status_code == 422
    assert _create(client, _create_payload(marking_config_id=str(uuid.uuid4()))).status_code == 404


def test_create_test_with_inline_custom_marking(client, engine_db, seeded_doc):
    res = _create(
        client,
        _create_payload(
            marking={
                "name": "Custom 2/-0.5",
                "correct_marks": 2.0,
                "incorrect_marks": -0.5,
                "unattempted_marks": 0.0,
            }
        ),
    )
    assert res.status_code == 201, res.text
    assert res.json()["marking_config"]["name"] == "Custom 2/-0.5"
    assert res.json()["marking_config"]["correct_marks"] == 2.0


def test_create_test_from_documents_source(client, engine_db, seeded_doc):
    doc_id, _ = seeded_doc
    res = _create(client, _create_payload(source_type="documents", source_ids=[str(doc_id)]))
    assert res.status_code == 201, res.text
    assert res.json()["source_type"] == "documents"
    res = _create(
        client,
        _create_payload(source_type="documents", source_ids=[str(uuid.uuid4())]),
    )
    assert res.status_code == 404  # another/missing document


def test_explicit_picks_duplicates_and_mismatch(client, engine_db, seeded_doc):
    _, by_number = seeded_doc
    q1 = by_number["1"]
    # Duplicate picks without the flag are a 422.
    res = _create(
        client,
        _create_payload(source_type="explicit", source_ids=[q1, q1], question_count=2),
    )
    assert res.status_code == 422, res.text
    assert res.json()["error"]["code"] == "duplicate_questions"
    # With the flag, the repetition is the caller's explicit choice.
    res = _create(
        client,
        _create_payload(
            source_type="explicit", source_ids=[q1, q1], question_count=2, allow_repetition=True
        ),
    )
    assert res.status_code == 201, res.text
    assert len(res.json()["snapshots"]) == 2
    assert res.json()["snapshots"][0]["question_id"] == res.json()["snapshots"][1]["question_id"]
    assert res.json()["allow_repetition"] is True
    # Count must match the pick list.
    res = _create(
        client,
        _create_payload(source_type="explicit", source_ids=[q1], question_count=2),
    )
    assert res.status_code == 422
    # An unknown pick needs the unknown flag.
    q2 = by_number["2"]
    res = _create(
        client,
        _create_payload(source_type="explicit", source_ids=[q1, q2], question_count=2),
    )
    assert res.status_code == 422
    res = _create(
        client,
        _create_payload(
            source_type="explicit", source_ids=[q1, q2], question_count=2, include_unknown=True
        ),
    )
    assert res.status_code == 201, res.text
    assert any(s["is_unknown"] for s in res.json()["snapshots"])
    # Another user's question is a 404.
    res = client.post(
        "/api/v1/tests",
        json=_create_payload(source_type="explicit", source_ids=[q1], question_count=1),
        headers=auth_headers("token-user-b"),
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Snapshot immutability (the graded rule)
# ---------------------------------------------------------------------------


def test_snapshot_frozen_after_bank_correction(client, engine_db, seeded_doc):
    doc_id, by_number = seeded_doc
    res = _create(client, _create_payload())
    assert res.status_code == 201, res.text
    test_id = res.json()["test_id"]
    # The key is only visible once the test is submitted, so
    # submit it (no answers — all unattempted) before reading
    # the frozen snapshot.
    res = client.post(f"/api/v1/tests/{test_id}/start", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    res = client.post(f"/api/v1/tests/{test_id}/submit", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    res = client.get(f"/api/v1/tests/{test_id}", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    before = res.json()["snapshots"]
    q1 = by_number["1"]
    q1_snap_before = next(s for s in before if s["question_id"] == q1)
    assert q1_snap_before["correct_index"] == 1  # B, from the trailing key
    # Correct the bank answer: B -> A. The bank changes; the test must not.
    res = client.post(
        f"/api/v1/documents/{doc_id}/questions/{q1}/corrections",
        json={"field": "answer", "new_value": "A", "reason": "M6 snapshot proof"},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    bank = client.get(f"/api/v1/questions/{q1}", headers=auth_headers("token-user-a")).json()
    assert bank["correct_index"] == 0  # the bank really changed
    assert bank["corrected"] is True
    # The test's snapshot is byte-identical to creation time.
    res = client.get(f"/api/v1/tests/{test_id}", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    after = res.json()["snapshots"]
    assert after == before
    q1_snap_after = next(s for s in after if s["question_id"] == q1)
    assert q1_snap_after["correct_index"] == 1
    assert q1_snap_after["question_text"] == q1_snap_before["question_text"]
    assert q1_snap_after["options"] == q1_snap_before["options"]


# ---------------------------------------------------------------------------
# Update / delete / ownership
# ---------------------------------------------------------------------------


def test_update_and_delete_only_before_attempt(client, engine_db, seeded_doc):
    res = _create(client, _create_payload())
    test_id = res.json()["test_id"]
    res = client.patch(
        f"/api/v1/tests/{test_id}",
        json={"name": "Renamed"},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    assert res.json()["title"] == "Renamed"
    # Simulate an attempt starting (M7 moves the status): edit and
    # delete are now forbidden.
    factory = engine_db
    session = factory()
    row = session.query(db.TestSession).filter(db.TestSession.id == uuid.UUID(test_id)).first()
    row.status = "in_progress"
    session.commit()
    session.close()
    res = client.patch(
        f"/api/v1/tests/{test_id}",
        json={"name": "Too late"},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 409
    res = client.delete(f"/api/v1/tests/{test_id}", headers=auth_headers("token-user-a"))
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "test_already_started"
    # Back to created: delete works and the test is gone.
    session = factory()
    row = session.query(db.TestSession).filter(db.TestSession.id == uuid.UUID(test_id)).first()
    row.status = "created"
    session.commit()
    session.close()
    res = client.delete(f"/api/v1/tests/{test_id}", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    assert res.json()["deleted"] is True
    res = client.get(f"/api/v1/tests/{test_id}", headers=auth_headers("token-user-a"))
    assert res.status_code == 404
    assert client.get("/api/v1/tests", headers=auth_headers("token-user-a")).json()["total"] == 0


def test_tests_are_per_user(client, engine_db, seeded_doc):
    res = _create(client, _create_payload())
    test_id = res.json()["test_id"]
    assert client.get("/api/v1/tests", headers=auth_headers("token-user-b")).json()["total"] == 0
    assert (
        client.get(f"/api/v1/tests/{test_id}", headers=auth_headers("token-user-b")).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/tests/{test_id}", headers=auth_headers("token-user-b")).status_code
        == 404
    )


def test_tests_require_auth(client, engine_db):
    assert client.get("/api/v1/tests").status_code == 401
    assert client.get("/api/v1/marking-configs").status_code == 401


# ---------------------------------------------------------------------------
# Answer-key withholding (security fix: GET /tests/{id} must not
# leak the key mid-test — the M9 exam-session rule, extended to
# the detail endpoints. Key visible only after submission.)
# ---------------------------------------------------------------------------


def _start(client, test_id):
    res = client.post(f"/api/v1/tests/{test_id}/start", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    return res


def _submit(client, test_id):
    res = client.post(f"/api/v1/tests/{test_id}/submit", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    return res


def _get_detail(client, test_id):
    res = client.get(f"/api/v1/tests/{test_id}", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    return res.json()


def test_get_test_withholds_key_while_created(client, engine_db, seeded_doc):
    res = _create(client, _create_payload(question_count=4, include_unknown=True))
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "created"
    # The create response itself carries no key.
    assert len(body["snapshots"]) == 4
    for snap in body["snapshots"]:
        assert snap["correct_index"] is None
        assert snap["answer_source"] is None
    # The unknown rows are still flagged — without the key.
    unknowns = [s for s in body["snapshots"] if s["is_unknown"]]
    assert len(unknowns) == 2
    assert sum(1 for s in body["snapshots"] if not s["is_unknown"]) == 2
    # Same on a fresh GET.
    detail = _get_detail(client, body["test_id"])
    assert detail["status"] == "created"
    assert all(s["correct_index"] is None for s in detail["snapshots"])
    assert all(s["answer_source"] is None for s in detail["snapshots"])


def test_get_test_withholds_key_while_in_progress(client, engine_db, seeded_doc):
    res = _create(client, _create_payload(question_count=2))
    assert res.status_code == 201, res.text
    test_id = res.json()["test_id"]
    _start(client, test_id)
    detail = _get_detail(client, test_id)
    assert detail["status"] == "in_progress"
    assert len(detail["snapshots"]) == 2
    for snap in detail["snapshots"]:
        assert snap["correct_index"] is None
        assert snap["answer_source"] is None
        assert snap["is_unknown"] is False  # both seeded rows are answered


def test_get_test_reveals_key_after_submit(client, engine_db, seeded_doc):
    res = _create(client, _create_payload(question_count=4, include_unknown=True))
    assert res.status_code == 201, res.text
    test_id = res.json()["test_id"]
    _start(client, test_id)
    _submit(client, test_id)
    detail = _get_detail(client, test_id)
    assert detail["status"] == "submitted"
    by_text = {s["question_text"]: s for s in detail["snapshots"]}
    assert by_text["What is the capital of Pakistan?"]["correct_index"] == 1
    assert by_text["What is the capital of Pakistan?"]["answer_source"] == "trailing-key"
    assert by_text["The largest desert of Pakistan is?"]["correct_index"] == 0
    assert by_text["The largest desert of Pakistan is?"]["answer_source"] == "inferred"
    unknown = by_text["Which river flows through Multan?"]
    assert unknown["correct_index"] == -1
    assert unknown["is_unknown"] is True


def test_retry_withholds_key_until_submitted(client, engine_db, seeded_doc):
    res = _create(client, _create_payload(question_count=2))
    assert res.status_code == 201, res.text
    test_id = res.json()["test_id"]
    _start(client, test_id)
    _submit(client, test_id)
    original = _get_detail(client, test_id)
    original_key = {s["question_id"]: s["correct_index"] for s in original["snapshots"]}
    assert all(v is not None for v in original_key.values())
    res = client.post(f"/api/v1/tests/{test_id}/retry", headers=auth_headers("token-user-a"))
    assert res.status_code == 201, res.text
    retry_id = res.json()["test_id"]
    assert res.json()["status"] == "created"
    assert all(s["correct_index"] is None for s in res.json()["snapshots"])
    # The retry carries the same frozen key — visible once the
    # retry itself is submitted.
    _start(client, retry_id)
    _submit(client, retry_id)
    retried = _get_detail(client, retry_id)
    assert {s["question_id"]: s["correct_index"] for s in retried["snapshots"]} == original_key


# ---------------------------------------------------------------------------
# Alembic 0006 — fresh DB, no create_all, no pre-created 015 tables
# ---------------------------------------------------------------------------


def test_migration_0006_fresh_db_has_documents_jobs_and_tests(tmp_path, monkeypatch):
    """M6 carry-over fix (M5 §5.2): a database built ONLY by
    ``alembic upgrade head`` — no create_all, no pre-created
    documents/jobs — now has every table the worker and the test
    builder need, and the PPSC default marking config is seeded.
    Before 0006 the worker failed here with 'no such table: jobs'.
    """
    from alembic.config import Config

    from alembic import command

    db_file = tmp_path / "alembic-m6.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_file}")

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_file}")
    try:
        names = set(inspect(engine).get_table_names())
        for expected in (
            "documents",
            "jobs",
            "marking_configs",
            "test_templates",
            "test_sessions",
            "test_question_snapshots",
        ):
            assert expected in names, f"missing after upgrade head: {expected}"
        with Session(engine) as session:
            configs = session.query(db.MarkingConfig).all()
            assert len(configs) == 1
            assert configs[0].name == "PPSC default"
            assert configs[0].is_default is True
            assert configs[0].correct_marks == 1.0
            assert configs[0].incorrect_marks == -0.25
            assert configs[0].unattempted_marks == 0.0
            # Worker-style inserts (the exact rows the upload flow
            # writes) commit on the migration-built database.
            doc = db.Document(
                user_id=uuid.uuid4(),
                title="M6 migration proof",
                storage_path="m6/proof.pdf",
                file_type="pdf",
                file_size_bytes=100,
                page_count=1,
            )
            session.add(doc)
            session.flush()
            session.add(db.Job(user_id=doc.user_id, document_id=doc.id, status="queued"))
            session.commit()
    finally:
        engine.dispose()
    # Downgrade is clean while no test rows exist, and it never
    # drops the 015-owned documents/jobs tables.
    command.downgrade(cfg, "0005_m5_subjects")
    engine = create_engine(f"sqlite:///{db_file}")
    try:
        names = set(inspect(engine).get_table_names())
        assert "test_sessions" not in names
        assert "marking_configs" not in names
        assert "documents" in names
        assert "jobs" in names
    finally:
        engine.dispose()
    command.upgrade(cfg, "head")


def test_migration_0006_documents_hash_index_is_partial(tmp_path, monkeypatch):
    """M6 fix (found by measuring in the M6 E2E): the (user_id,
    content_hash) unique index is PARTIAL — live rows only.
    The 015 plain unique index made delete-then-re-upload of
    the same file fail with 500 (UNIQUE constraint failed),
    because the soft-deleted row still held the unique slot
    while the dedup lookup correctly ignored it. On a database
    built ONLY by ``alembic upgrade head``:
    - a deleted row + a live row with the same user + hash
      must BOTH exist (the re-upload case);
    - two LIVE rows with the same user + hash must still fail
      (dedup preserved);
    - a different user with the same hash is unaffected.
    Proven to fail on the old plain unique index (the second
    insert raises IntegrityError there).
    """
    from datetime import datetime

    from alembic.config import Config
    from sqlalchemy.exc import IntegrityError

    from alembic import command

    db_file = tmp_path / "alembic-m6-hash.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_file}")

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")

    user = uuid.uuid4()
    content_hash = "a" * 64
    engine = create_engine(f"sqlite:///{db_file}")
    try:
        with Session(engine) as session:
            deleted = db.Document(
                user_id=user,
                title="Deleted first upload",
                storage_path="m6/deleted.pdf",
                file_type="pdf",
                file_size_bytes=100,
                page_count=1,
                content_hash=content_hash,
                deleted_at=datetime.now(),
            )
            session.add(deleted)
            session.commit()
            # The re-upload: same user + same hash, live row.
            live = db.Document(
                user_id=user,
                title="Re-uploaded after delete",
                storage_path="m6/live.pdf",
                file_type="pdf",
                file_size_bytes=100,
                page_count=1,
                content_hash=content_hash,
            )
            session.add(live)
            session.commit()
            # A second live row with the same hash still violates
            # the dedup rule.
            duplicate = db.Document(
                user_id=user,
                title="Duplicate live upload",
                storage_path="m6/dup.pdf",
                file_type="pdf",
                file_size_bytes=100,
                page_count=1,
                content_hash=content_hash,
            )
            session.add(duplicate)
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
            # Another user with the same hash is unaffected.
            other = db.Document(
                user_id=uuid.uuid4(),
                title="Same file, other user",
                storage_path="m6/other.pdf",
                file_type="pdf",
                file_size_bytes=100,
                page_count=1,
                content_hash=content_hash,
            )
            session.add(other)
            session.commit()
    finally:
        engine.dispose()


def test_migration_0006_downgrade_refuses_with_test_rows(tmp_path, monkeypatch):
    """Doc 03 §6: a downgrade never deletes user data silently."""
    from alembic.config import Config

    from alembic import command

    db_file = tmp_path / "alembic-m6-refuse.db"
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
            session.add(
                db.TestSession(
                    user_id=template.user_id,
                    template_id=template.id,
                    title="Refuse me",
                    question_count=1,
                    marking_config_id=config.id,
                    status="created",
                )
            )
            session.commit()
    finally:
        engine.dispose()
    with pytest.raises(RuntimeError, match="Refusing downgrade"):
        command.downgrade(cfg, "0005_m5_subjects")
