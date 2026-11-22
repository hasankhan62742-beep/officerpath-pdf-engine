# OfficerPath AI — Phase 2, M8
# Results + student analytics (GAP-7) and question collections
# (GAP-8: bookmarks + mistake notebook) + Alembic 0008.
#
# Seed: one document with 7 questions (6 answered + 1 unknown)
# persisted through the Phase 1 store — the same rows the worker
# writes. Subjects are assigned by hand (never auto-classified):
# Q1-Q3 -> General Knowledge (Q1 also has topic "Capitals"),
# Q4-Q5 -> Current Affairs, Q6 -> none (Uncategorised), Q7 ->
# unknown, no subject. The standard attempt answers Q1/Q2/Q4
# correct, Q3/Q5 incorrect, Q6 unattempted, Q7 marked for
# review only — so every breakdown number below is hand-checked
# arithmetic, quoted in the test names.
#
# Standard attempt, PPSC default (+1 / -0.25 / 0):
#   overall: correct 3, incorrect 2, unattempted 1, unknown 1,
#     total 3.0 - 0.50 = 2.5, max 6.0, 41.67%
#   General Knowledge: scored 3, correct 2, incorrect 1,
#     marks 1.75, max 3.0, accuracy 66.67
#   Current Affairs: scored 2, correct 1, incorrect 1,
#     marks 0.75, max 2.0, accuracy 50.00
#   Uncategorised: scored 1 (Q6, unattempted), marks 0.0,
#     max 1.0, accuracy 0.00
#   Topic "Capitals": scored 1, correct 1, marks 1.0, max 1.0,
#     accuracy 100.00
#   Topic Uncategorised: scored 5, correct 2, incorrect 2,
#     unattempted 1, marks 1.5, max 5.0, accuracy 40.00
#   Mistakes: Q3, Q5 (incorrect only — correct, unattempted
#     and unknown create NO mistake row).

import json
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
    def q(number, text, options, correct_index, page):
        return ResolvedMCQ(
            number=number,
            text=text,
            options=options,
            correct_index=correct_index,
            answer_source="trailing-key" if correct_index >= 0 else "",
            confidence=1.0,
            raw_confidence=1.0,
            verified=True,
            status="answered" if correct_index >= 0 else "unknown",
            page=page,
            paper="Paper 66",
        )

    return MatchedDocument(
        questions=[
            q(
                1,
                "What is the capital of Pakistan?",
                ["Karachi", "Islamabad", "Lahore", "Quetta"],
                1,
                1,
            ),
            q(2, "Which river flows through Multan?", ["Indus", "Chenab", "Ravi", "Jhelum"], 0, 1),
            q(
                3,
                "The largest desert of Pakistan is?",
                ["Thar", "Cholistan", "Kharan", "Thal"],
                2,
                1,
            ),
            q(4, "Which ocean is the largest?", ["Atlantic", "Indian", "Pacific", "Arctic"], 3, 2),
            q(5, "What is 2 + 2?", ["3", "4", "5", "6"], 1, 2),
            q(
                6,
                "Which planet is known as the Red Planet?",
                ["Venus", "Mars", "Jupiter", "Saturn"],
                1,
                2,
            ),
            q(
                7,
                "Which ocean is the smallest?",
                ["Atlantic", "Indian", "Pacific", "Arctic"],
                -1,
                2,
            ),
        ],
        qa_pairs=[],
        pending=[],
        counts={"questions": 7, "answered": 6, "unknown": 1, "pending": 0},
    )


@pytest.fixture()
def seeded_doc(engine_db):
    """7-question document + hand-assigned subjects/topics.
    Returns (doc_id, by_number, subject_ids, topic_id)."""
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
            content_hash="c" * 64,
        )
    )
    session.add(db.Job(id=job_id, user_id=uuid.UUID(USER_A), document_id=doc_id, status="done"))
    session.commit()
    persist_matched_document(session, document_id=doc_id, job_id=job_id, matched=_matched())
    rows = (
        session.query(db.ExtractedQuestion).filter(db.ExtractedQuestion.document_id == doc_id).all()
    )
    by_number = {row.question_number: str(row.id) for row in rows}
    gk = db.Subject(name="General Knowledge", slug="general-knowledge")
    ca = db.Subject(name="Current Affairs", slug="current-affairs")
    session.add_all([gk, ca])
    session.flush()
    capitals = db.Topic(subject_id=gk.id, name="Capitals", slug="capitals")
    session.add(capitals)
    session.flush()
    by_uuid = {row.question_number: row.id for row in rows}
    assignments = [
        (by_uuid["1"], gk.id, capitals.id),
        (by_uuid["2"], gk.id, None),
        (by_uuid["3"], gk.id, None),
        (by_uuid["4"], ca.id, None),
        (by_uuid["5"], ca.id, None),
    ]
    for question_id, subject_id, topic_id in assignments:
        session.add(
            db.QuestionSubject(
                question_id=question_id,
                subject_id=subject_id,
                topic_id=topic_id,
                assigned_by=uuid.UUID(USER_A),
            )
        )
    session.commit()
    out = (
        doc_id,
        by_number,
        {"gk": str(gk.id), "ca": str(ca.id)},
        str(capitals.id),
    )
    session.close()
    return out


# --- API helpers -----------------------------------------------------------


def _create_explicit(client, question_ids, name="M8 Test", include_unknown=True, **overrides):
    payload = {
        "name": name,
        "question_count": len(question_ids),
        "source_type": "explicit",
        "source_ids": question_ids,
        "include_unknown": include_unknown,
    }
    payload.update(overrides)
    return client.post("/api/v1/tests", json=payload, headers=auth_headers("token-user-a"))


def _snapshot_map(client, test_id) -> dict:
    """question_id -> snapshot row, from the exam session."""
    res = client.get(f"/api/v1/tests/{test_id}/session", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    return {s["question_id"]: s for s in res.json()["snapshots"]}


# The standard attempt: Q1/Q2/Q4 correct, Q3/Q5 incorrect,
# Q6 unattempted, Q7 marked-for-review only. (Q5 "2 + 2" is
# correct B=1, so the incorrect answer is C=2.)
STANDARD_ANSWERS = {"1": 1, "2": 0, "3": 0, "4": 3, "5": 2}  # number -> selected_index


def _result_row(session, result_id):
    """Fetch one stored TestResult row by its (dashed) id."""
    return session.query(db.TestResult).filter(db.TestResult.id == uuid.UUID(result_id)).first()


def _run_standard_attempt(client, by_number, name="M8 Test") -> tuple[str, dict]:
    """Create (explicit, all 7), start, answer the standard mix,
    submit. Returns (test_id, submit response body)."""
    question_ids = [by_number[str(n)] for n in range(1, 8)]
    res = _create_explicit(client, question_ids, name=name)
    assert res.status_code == 201, res.text
    test_id = res.json()["test_id"]
    res = client.post(f"/api/v1/tests/{test_id}/start", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    snaps = _snapshot_map(client, test_id)
    items = []
    for number, selected in STANDARD_ANSWERS.items():
        qid = by_number[number]
        items.append({"snapshot_id": snaps[qid]["snapshot_id"], "selected_index": selected})
    q7 = by_number["7"]
    items.append(
        {"snapshot_id": snaps[q7]["snapshot_id"], "selected_index": None, "marked_for_review": True}
    )
    res = client.post(
        f"/api/v1/tests/{test_id}/answers",
        json={"answers": items},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    res = client.post(f"/api/v1/tests/{test_id}/submit", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    return test_id, res.json()


def _result(client, test_id, token="token-user-a"):
    return client.get(f"/api/v1/tests/{test_id}/result", headers=auth_headers(token))


def _bucket(breakdown, name):
    for bucket in breakdown or []:
        if bucket["name"] == name:
            return bucket
    raise AssertionError(f"no bucket named {name!r} in {breakdown}")


# ---------------------------------------------------------------------------
# Breakdowns at submit
# ---------------------------------------------------------------------------


def test_submit_writes_hand_checked_breakdowns(client, engine_db, seeded_doc):
    _, by_number, _, _ = seeded_doc
    test_id, submit = _run_standard_attempt(client, by_number)
    assert submit["correct"] == 3
    assert submit["incorrect"] == 2
    assert submit["unattempted"] == 1
    assert submit["unknown_count"] == 1
    assert submit["total_marks"] == 2.5
    assert submit["max_marks"] == 6.0
    assert submit["percentage"] == 41.67

    res = _result(client, test_id)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total_marks"] == 2.5  # stored row, exactly

    gk = _bucket(body["subject_breakdown"], "General Knowledge")
    assert gk == {
        "key": gk["key"],
        "name": "General Knowledge",
        "slug": "general-knowledge",
        "scored": 3,
        "correct": 2,
        "incorrect": 1,
        "unattempted": 0,
        "marks": 1.75,
        "max_marks": 3.0,
        "accuracy": 66.67,
    }
    ca = _bucket(body["subject_breakdown"], "Current Affairs")
    assert ca["scored"] == 2 and ca["correct"] == 1 and ca["incorrect"] == 1
    assert ca["unattempted"] == 0 and ca["marks"] == 0.75 and ca["max_marks"] == 2.0
    assert ca["accuracy"] == 50.0
    unc = _bucket(body["subject_breakdown"], "Uncategorised")
    assert unc["scored"] == 1 and unc["correct"] == 0 and unc["unattempted"] == 1
    assert unc["marks"] == 0.0 and unc["max_marks"] == 1.0 and unc["accuracy"] == 0.0
    # The unknown question is in NO bucket: scored sums to 6.
    assert sum(b["scored"] for b in body["subject_breakdown"]) == 6

    capitals = _bucket(body["topic_breakdown"], "Capitals")
    assert capitals["scored"] == 1 and capitals["correct"] == 1
    assert capitals["marks"] == 1.0 and capitals["max_marks"] == 1.0
    assert capitals["accuracy"] == 100.0
    t_unc = _bucket(body["topic_breakdown"], "Uncategorised")
    assert t_unc["scored"] == 5 and t_unc["correct"] == 2 and t_unc["incorrect"] == 2
    assert t_unc["unattempted"] == 1 and t_unc["marks"] == 1.5 and t_unc["max_marks"] == 5.0
    assert t_unc["accuracy"] == 40.0

    # Weak/strong: only General Knowledge has >= 3 scored, so it
    # is both weakest and strongest; Uncategorised never counts.
    assert body["weak_areas"] == [
        {"subject_name": "General Knowledge", "accuracy": 66.67, "scored": 3}
    ]
    assert body["strong_areas"] == [
        {"subject_name": "General Knowledge", "accuracy": 66.67, "scored": 3}
    ]


def test_weak_strong_distinct_when_two_subjects_qualify(client, engine_db, seeded_doc):
    """Reassign Q6 to Current Affairs (so CA has 3 scored):
    weakest = CA 33.33, strongest = GK 66.67."""
    factory = engine_db
    _, by_number, subjects, _ = seeded_doc
    session = factory()
    session.add(
        db.QuestionSubject(
            question_id=uuid.UUID(by_number["6"]),
            subject_id=uuid.UUID(subjects["ca"]),
            topic_id=None,
            assigned_by=uuid.UUID(USER_A),
        )
    )
    session.commit()
    session.close()

    test_id, _ = _run_standard_attempt(client, by_number)
    body = _result(client, test_id).json()
    assert body["weak_areas"] == [
        {"subject_name": "Current Affairs", "accuracy": 33.33, "scored": 3}
    ]
    assert body["strong_areas"] == [
        {"subject_name": "General Knowledge", "accuracy": 66.67, "scored": 3}
    ]


def test_first_assignment_wins_for_breakdowns(client, engine_db, seeded_doc):
    """Q1 gets a SECOND, later assignment to Current Affairs —
    the breakdown must still count Q1 under General Knowledge
    (its earliest assignment)."""
    factory = engine_db
    _, by_number, subjects, _ = seeded_doc
    session = factory()
    # Explicitly later created_at: the fixture rows and this one
    # would otherwise share a created_at second (SQLite's
    # CURRENT_TIMESTAMP has second precision), and the
    # "earliest wins" rule needs a defined order to test.
    session.add(
        db.QuestionSubject(
            question_id=uuid.UUID(by_number["1"]),
            subject_id=uuid.UUID(subjects["ca"]),
            topic_id=None,
            assigned_by=uuid.UUID(USER_A),
            created_at=datetime.now(UTC).replace(microsecond=0) + timedelta(hours=1),
        )
    )
    session.commit()
    session.close()

    test_id, _ = _run_standard_attempt(client, by_number)
    body = _result(client, test_id).json()
    gk = _bucket(body["subject_breakdown"], "General Knowledge")
    assert gk["scored"] == 3  # Q1 still counted here
    ca = _bucket(body["subject_breakdown"], "Current Affairs")
    assert ca["scored"] == 2  # Q1 did NOT move to CA


def test_backfill_fills_m7_null_breakdowns(client, engine_db, seeded_doc):
    """An M7 result stored with NULL breakdowns shows breakdowns
    on read, and the row is persisted afterwards."""
    factory = engine_db
    _, by_number, _, _ = seeded_doc
    test_id, submit = _run_standard_attempt(client, by_number)
    assert submit["total_marks"] == 2.5

    # Simulate the M7 row: wipe the breakdowns in the DB.
    session = factory()
    row = _result_row(session, submit["result_id"])
    assert row is not None
    row.subject_breakdown = None
    row.topic_breakdown = None
    session.commit()
    session.close()

    res = _result(client, test_id)
    assert res.status_code == 200, res.text
    body = res.json()
    gk = _bucket(body["subject_breakdown"], "General Knowledge")
    assert gk["scored"] == 3 and gk["marks"] == 1.75 and gk["accuracy"] == 66.67
    assert body["total_marks"] == 2.5  # stored numbers untouched

    # Persisted: a fresh read of the row shows breakdowns.
    session = factory()
    row = _result_row(session, submit["result_id"])
    assert row.subject_breakdown is not None
    assert row.topic_breakdown is not None
    session.close()


def test_result_before_submit_is_404(client, engine_db, seeded_doc):
    _, by_number, _, _ = seeded_doc
    question_ids = [by_number[str(n)] for n in range(1, 8)]
    res = _create_explicit(client, question_ids)
    assert res.status_code == 201, res.text
    assert _result(client, res.json()["test_id"]).status_code == 404


# ---------------------------------------------------------------------------
# Review items
# ---------------------------------------------------------------------------


def test_review_items_show_stored_truth_only(client, engine_db, seeded_doc):
    _, by_number, _, _ = seeded_doc
    test_id, _ = _run_standard_attempt(client, by_number)
    body = _result(client, test_id).json()
    review = body["review"]
    assert [item["position"] for item in review] == [1, 2, 3, 4, 5, 6, 7]
    assert [item["status"] for item in review] == [
        "correct",
        "correct",
        "incorrect",
        "correct",
        "incorrect",
        "unattempted",
        "unknown",
    ]
    # The unknown item is never shown as correct/incorrect and
    # carries its stored correct_index -1.
    unknown = review[6]
    assert unknown["correct_index"] == -1
    assert unknown["selected_index"] is None
    assert unknown["marked_for_review"] is True
    # Correct/incorrect items carry the student's selection and
    # the stored evidence source — no explanations invented.
    assert review[2]["selected_index"] == 0
    assert review[2]["correct_index"] == 2
    assert review[2]["answer_source"] == "trailing-key"
    assert review[0]["question_text"] == "What is the capital of Pakistan?"
    assert review[0]["options"][1]["text"] == "Islamabad"


def test_review_bookmark_flag_follows_collection(client, engine_db, seeded_doc):
    _, by_number, _, _ = seeded_doc
    test_id, _ = _run_standard_attempt(client, by_number)
    q1 = by_number["1"]
    res = client.post(
        "/api/v1/collections",
        json={"question_id": q1, "collection_type": "bookmark"},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 201, res.text
    body = _result(client, test_id).json()
    item = next(i for i in body["review"] if i["question_id"] == q1)
    assert item["is_bookmarked"] is True
    assert item["bookmark_id"] == res.json()["id"]
    other = next(i for i in body["review"] if i["question_id"] == by_number["2"])
    assert other["is_bookmarked"] is False
    assert other["bookmark_id"] is None


# ---------------------------------------------------------------------------
# Mistake rows from submit
# ---------------------------------------------------------------------------


def test_mistake_rows_created_once_for_incorrect_only(client, engine_db, seeded_doc):
    _, by_number, _, _ = seeded_doc
    test_id, submit = _run_standard_attempt(client, by_number)
    res = client.get(
        "/api/v1/collections?collection_type=mistake",
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    mistakes = res.json()["collections"]
    assert res.json()["total"] == 2
    assert {m["question_id"] for m in mistakes} == {by_number["3"], by_number["5"]}
    # Correct (Q1/Q2/Q4), unattempted (Q6) and unknown (Q7)
    # create NO mistake row.
    assert by_number["1"] not in {m["question_id"] for m in mistakes}
    # A re-submit (idempotent, same result) creates no duplicates.
    res2 = client.post(f"/api/v1/tests/{test_id}/submit", headers=auth_headers("token-user-a"))
    assert res2.status_code == 200
    assert res2.json()["result_id"] == submit["result_id"]
    res = client.get(
        "/api/v1/collections?collection_type=mistake",
        headers=auth_headers("token-user-a"),
    )
    assert res.json()["total"] == 2


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


def test_history_lists_newest_first(client, engine_db, seeded_doc):
    _, by_number, _, _ = seeded_doc
    test_id_1, _ = _run_standard_attempt(client, by_number, name="M8 First")
    question_ids = [by_number["1"], by_number["2"]]
    res = _create_explicit(client, question_ids, name="M8 Second", include_unknown=False)
    assert res.status_code == 201, res.text
    test_id_2 = res.json()["test_id"]
    client.post(f"/api/v1/tests/{test_id_2}/start", headers=auth_headers("token-user-a"))
    snaps = _snapshot_map(client, test_id_2)
    res = client.post(
        f"/api/v1/tests/{test_id_2}/answers",
        json={
            "answers": [
                {"snapshot_id": snaps[by_number["1"]]["snapshot_id"], "selected_index": 1},
                {"snapshot_id": snaps[by_number["2"]]["snapshot_id"], "selected_index": 0},
            ]
        },
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    res = client.post(f"/api/v1/tests/{test_id_2}/submit", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    assert res.json()["percentage"] == 100.0

    res = client.get("/api/v1/results", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 2
    # Newest first — and the two stored rows give a real
    # compare-over-time pair (41.67 then 100.0).
    assert [r["test_id"] for r in body["results"]] == [test_id_2, test_id_1]
    assert [r["percentage"] for r in body["results"]] == [100.0, 41.67]
    assert body["results"][1]["subject_breakdown"] is not None


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------


def _canonical_snapshots(client, test_id) -> str:
    res = client.get(f"/api/v1/tests/{test_id}", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    snaps = res.json()["snapshots"]
    stripped = [{k: v for k, v in snap.items() if k != "snapshot_id"} for snap in snaps]
    return json.dumps(stripped, sort_keys=True)


def test_retry_keeps_snapshots_byte_identical(client, engine_db, seeded_doc):
    _, by_number, _, _ = seeded_doc
    test_id, _ = _run_standard_attempt(client, by_number)
    before = _canonical_snapshots(client, test_id)
    res = client.post(f"/api/v1/tests/{test_id}/retry", headers=auth_headers("token-user-a"))
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "created"
    assert body["retried_from_test_id"] == test_id
    assert body["test_id"] != test_id
    assert _canonical_snapshots(client, body["test_id"]) == before
    # The retry is a fresh attempt: it can be started.
    res = client.post(
        f"/api/v1/tests/{body['test_id']}/start", headers=auth_headers("token-user-a")
    )
    assert res.status_code == 200, res.text


def test_retry_requires_submitted(client, engine_db, seeded_doc):
    _, by_number, _, _ = seeded_doc
    question_ids = [by_number[str(n)] for n in range(1, 8)]
    res = _create_explicit(client, question_ids)
    assert res.status_code == 201, res.text
    test_id = res.json()["test_id"]
    res = client.post(f"/api/v1/tests/{test_id}/retry", headers=auth_headers("token-user-a"))
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "test_not_submitted"


# ---------------------------------------------------------------------------
# Practice from mistakes
# ---------------------------------------------------------------------------


def test_from_mistakes_uses_original_snapshots(client, engine_db, seeded_doc):
    factory = engine_db
    _, by_number, _, _ = seeded_doc
    test_id, _ = _run_standard_attempt(client, by_number)

    res = client.post(
        "/api/v1/tests/from-mistakes",
        json={"name": "Mistake practice"},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["question_count"] == 2
    assert body["source_type"] == "mistakes"
    assert body["status"] == "created"
    assert body["skipped_question_ids"] == []
    snaps = body["snapshots"]
    assert {s["question_id"] for s in snaps} == {by_number["3"], by_number["5"]}
    # The practice snapshots carry the ORIGINAL correct answers.
    by_qid = {s["question_id"]: s for s in snaps}
    assert by_qid[by_number["3"]]["correct_index"] == 2
    assert by_qid[by_number["5"]]["correct_index"] == 1

    # Now "correct" the bank: Q3's live answer changes from C to A.
    # The practice test must NOT change — its snapshots are frozen
    # copies of the original attempt.
    session = factory()
    q3 = uuid.UUID(by_number["3"])
    answer = (
        session.query(db.ExtractedAnswer)
        .filter(db.ExtractedAnswer.question_id == q3)
        .order_by(db.ExtractedAnswer.created_at.desc())
        .first()
    )
    assert answer is not None
    answer.resolved_label = "A"
    session.commit()
    session.close()

    res = client.get(f"/api/v1/tests/{body['test_id']}", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    snaps = res.json()["snapshots"]
    by_qid = {s["question_id"]: s for s in snaps}
    assert by_qid[by_number["3"]]["correct_index"] == 2  # still the original C
    assert by_qid[by_number["3"]]["question_text"] == "The largest desert of Pakistan is?"


def test_from_mistakes_subset_and_empty_notebook(client, engine_db, seeded_doc):
    _, by_number, _, _ = seeded_doc
    # Empty notebook first: 422, honest.
    res = client.post(
        "/api/v1/tests/from-mistakes",
        json={"name": "Nothing to practise"},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "no_mistakes"

    test_id, _ = _run_standard_attempt(client, by_number)
    assert test_id
    res = client.post(
        "/api/v1/tests/from-mistakes",
        json={"name": "Just Q3", "question_ids": [by_number["3"]]},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 201, res.text
    assert res.json()["question_count"] == 1
    assert res.json()["snapshots"][0]["question_id"] == by_number["3"]
    # A question that is NOT a mistake cannot be practised.
    res = client.post(
        "/api/v1/tests/from-mistakes",
        json={"name": "Not a mistake", "question_ids": [by_number["1"]]},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Collections API
# ---------------------------------------------------------------------------


def test_bookmark_idempotent_note_and_delete(client, engine_db, seeded_doc):
    _, by_number, _, _ = seeded_doc
    q1 = by_number["1"]
    res = client.post(
        "/api/v1/collections",
        json={"question_id": q1, "collection_type": "bookmark"},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 201, res.text
    first = res.json()
    assert first["already_exists"] is False
    assert first["question"]["text"] == "What is the capital of Pakistan?"
    assert first["question"]["correct_index"] == 1
    assert first["question"]["options"] == ["Karachi", "Islamabad", "Lahore", "Quetta"]

    # Bookmarking twice is idempotent-200, one row, never 409.
    res = client.post(
        "/api/v1/collections",
        json={"question_id": q1, "collection_type": "bookmark"},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    assert res.json()["already_exists"] is True
    assert res.json()["id"] == first["id"]

    res = client.get(
        "/api/v1/collections?collection_type=bookmark", headers=auth_headers("token-user-a")
    )
    assert res.json()["total"] == 1

    # Note edit, then clear.
    res = client.patch(
        f"/api/v1/collections/{first['id']}",
        json={"note": "Revise capitals before the exam."},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    assert res.json()["note"] == "Revise capitals before the exam."
    res = client.patch(
        f"/api/v1/collections/{first['id']}",
        json={"note": None},
        headers=auth_headers("token-user-a"),
    )
    assert res.json()["note"] is None

    res = client.delete(f"/api/v1/collections/{first['id']}", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    assert res.json()["deleted"] is True
    assert (
        client.delete(
            f"/api/v1/collections/{first['id']}", headers=auth_headers("token-user-a")
        ).status_code
        == 404
    )


def test_collections_mistake_cannot_be_created_by_api(client, engine_db, seeded_doc):
    _, by_number, _, _ = seeded_doc
    res = client.post(
        "/api/v1/collections",
        json={"question_id": by_number["1"], "collection_type": "mistake"},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 422
    res = client.post(
        "/api/v1/collections",
        json={"question_id": by_number["1"], "collection_type": "wrong-type"},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 422


def test_collections_owner_isolation(client, engine_db, seeded_doc):
    _, by_number, _, _ = seeded_doc
    test_id, _ = _run_standard_attempt(client, by_number)
    # USER_B sees none of USER_A's rows and none of the tests.
    res = client.get("/api/v1/collections", headers=auth_headers("token-user-b"))
    assert res.status_code == 200, res.text
    assert res.json()["total"] == 0
    assert _result(client, test_id, token="token-user-b").status_code == 404
    assert (
        client.post(
            f"/api/v1/tests/{test_id}/retry", headers=auth_headers("token-user-b")
        ).status_code
        == 404
    )
    # USER_B cannot bookmark USER_A's question (404, never leaks).
    res = client.post(
        "/api/v1/collections",
        json={"question_id": by_number["1"], "collection_type": "bookmark"},
        headers=auth_headers("token-user-b"),
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Alembic 0008
# ---------------------------------------------------------------------------


def test_migration_0008_fresh_db_has_collections_table(tmp_path, monkeypatch):
    """A database built ONLY by ``alembic upgrade head`` has the
    M8 collections table, and a downgrade to 0007 drops it."""
    from alembic.config import Config

    from alembic import command

    db_file = tmp_path / "alembic-m8.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_file}")

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_file}")
    try:
        names = set(inspect(engine).get_table_names())
        assert "student_question_collections" in names
    finally:
        engine.dispose()
    command.downgrade(cfg, "0007_m7_exam")
    engine = create_engine(f"sqlite:///{db_file}")
    try:
        names = set(inspect(engine).get_table_names())
        assert "student_question_collections" not in names
        assert "test_results" in names  # M7 tables untouched
    finally:
        engine.dispose()
    command.upgrade(cfg, "head")


def test_migration_0008_downgrade_refuses_with_collection_rows(tmp_path, monkeypatch):
    """Doc 03 §6: a downgrade never deletes user data silently."""
    from alembic.config import Config

    from alembic import command

    db_file = tmp_path / "alembic-m8-refuse.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_file}")

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{db_file}")
    try:
        with Session(engine) as session:
            session.add(
                db.StudentQuestionCollection(
                    user_id=uuid.uuid4(),
                    question_id=uuid.uuid4(),
                    collection_type="bookmark",
                    note=None,
                )
            )
            session.commit()
    finally:
        engine.dispose()
    with pytest.raises(RuntimeError, match="Refusing downgrade"):
        command.downgrade(cfg, "0007_m7_exam")
    command.upgrade(cfg, "head")
