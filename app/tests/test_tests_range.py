# OfficerPath AI — Phase 2, M12
# Section tabs + reading mode + test range.
#
# Seed: one private document (USER_A) with 10 questions split
# across two sections of one subtopic — "Algebra — Section 1"
# (numbers 1-5) and "Algebra — Section 2" (numbers 1-5, of
# which number 5 is unknown) — plus an empty third section
# ("Geometry — Section 1"), plus a shared bank document
# (USER_ADMIN) with 2 questions in Section 1. Printed numbers
# restart at 1 in every section, so bank order is section
# first, then number — the sample/ordering assertions below
# would fail if the pool were ordered by number alone.

import uuid

import pytest

from app.db import models as db
from app.pipeline.matching.models import MatchedDocument, ResolvedMCQ
from app.pipeline.matching.store import persist_matched_document
from app.tests.conftest import USER_A, USER_ADMIN, auth_headers


def _matched(questions):
    """questions: list of (number, text, correct_index or -1)."""
    items = []
    for number, text, correct_index in questions:
        items.append(
            ResolvedMCQ(
                number=number,
                text=text,
                options=["A1", "B1", "C1", "D1"],
                correct_index=correct_index,
                answer_source="trailing-key" if correct_index >= 0 else "",
                confidence=1.0 if correct_index >= 0 else 0.0,
                raw_confidence=1.0 if correct_index >= 0 else 0.0,
                verified=correct_index >= 0,
                status="answered" if correct_index >= 0 else "unknown",
                page=1,
                paper="Range Paper",
            )
        )
    return MatchedDocument(
        questions=items,
        qa_pairs=[],
        pending=[],
        counts={
            "questions": len(items),
            "answered": sum(1 for _, _, c in questions if c >= 0),
            "unknown": sum(1 for _, _, c in questions if c < 0),
            "pending": 0,
        },
    )


def _seed_doc(session, owner, title, questions, is_shared=None, content_hash="c" * 64):
    doc_id = uuid.uuid4()
    job_id = uuid.uuid4()
    doc = db.Document(
        id=doc_id,
        user_id=uuid.UUID(owner),
        title=title,
        storage_path="inline-parse",
        file_type="pdf",
        file_size_bytes=1234,
        page_count=1,
        content_hash=content_hash,
    )
    if is_shared is not None:
        doc.is_shared = is_shared
    session.add(doc)
    session.add(db.Job(id=job_id, user_id=uuid.UUID(owner), document_id=doc_id, status="done"))
    session.commit()
    persist_matched_document(
        session, document_id=doc_id, job_id=job_id, matched=_matched(questions)
    )
    rows = (
        session.query(db.ExtractedQuestion).filter(db.ExtractedQuestion.document_id == doc_id).all()
    )
    return doc_id, {row.question_number: str(row.id) for row in rows}


@pytest.fixture()
def seeded_sections(engine_db):
    """USER_A private doc: Algebra s1 Q1-5, Algebra s2 Q1-5
    (s2 Q5 unknown). USER_ADMIN shared doc: Algebra s1 Q6-7,
    so Section 1 mixes private + shared questions for USER_A
    (7 total) while USER_B sees only the 2 shared ones.
    Subject Mathematics with topics Algebra s1/s2 + Geometry
    s1 (empty). One question carries a stored explanation."""
    factory = engine_db
    session = factory()
    subject = db.Subject(name="Mathematics", slug="mathematics")
    session.add(subject)
    session.flush()
    t1 = db.Topic(subject_id=subject.id, name="Algebra — Section 1", slug="algebra-s1")
    t2 = db.Topic(subject_id=subject.id, name="Algebra — Section 2", slug="algebra-s2")
    t3 = db.Topic(subject_id=subject.id, name="Geometry — Section 1", slug="geometry-s1")
    session.add_all([t1, t2, t3])
    session.flush()

    def _assign(doc_id, topic):
        rows = (
            session.query(db.ExtractedQuestion)
            .filter(db.ExtractedQuestion.document_id == doc_id)
            .all()
        )
        for row in rows:
            session.add(
                db.QuestionSubject(
                    question_id=row.id,
                    subject_id=subject.id,
                    topic_id=topic.id,
                    assigned_by=uuid.UUID(USER_A),
                )
            )

    doc_id, by_number = _seed_doc(
        session,
        USER_A,
        "Range Paper",
        [(n, f"Algebra s1 question {n}", 0) for n in range(1, 6)],
    )
    _assign(doc_id, t1)
    doc2_id, _ = _seed_doc(
        session,
        USER_A,
        "Range Paper 2",
        [(n, f"Algebra s2 question {n}", 0 if n < 5 else -1) for n in range(1, 6)],
        content_hash="d" * 64,
    )
    _assign(doc2_id, t2)
    # Stored verbatim explanation on s1 Q1 (reading mode shows
    # it; the other questions have none — never invented).
    q1 = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.id == uuid.UUID(by_number["1"]))
        .first()
    )
    q1.explanation = "Because 1 + 1 = 2, as shown in the worked solution."
    admin_doc, admin_qs = _seed_doc(
        session,
        USER_ADMIN,
        "Shared Bank — Algebra",
        [(6, "Shared algebra question 1", 1), (7, "Shared algebra question 2", 2)],
        is_shared=True,
        content_hash="e" * 64,
    )
    _assign(admin_doc, t1)
    session.commit()
    out = {
        "subject": str(subject.id),
        "t1": str(t1.id),
        "t2": str(t2.id),
        "t3": str(t3.id),
        "doc": str(doc_id),
        "doc2": str(doc2_id),
        "admin_doc": str(admin_doc),
        "admin_qs": admin_qs,
    }
    session.close()
    return out


def _availability(client, params, token="token-user-a"):
    return client.get(
        "/api/v1/tests/availability", params=params, headers=auth_headers(token)
    )


def _create(client, payload, token="token-user-a"):
    return client.post("/api/v1/tests", json=payload, headers=auth_headers(token))


# ---------------------------------------------------------------------------
# Availability: per-topic breakdown + range
# ---------------------------------------------------------------------------


def test_availability_by_topic_breakdown(client, engine_db, seeded_sections):
    res = _availability(
        client,
        {
            "source_type": "topics",
            "topic_ids": [
                seeded_sections["t1"],
                seeded_sections["t2"],
                seeded_sections["t3"],
            ],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["available"] == 11  # s1: 5 own + 2 shared; s2: 4 (Q5 unknown excluded)
    assert body["excluded_unknown"] == 1
    by_topic = {row["topic_id"]: row for row in body["by_topic"]}
    assert by_topic[seeded_sections["t1"]]["available"] == 7
    assert by_topic[seeded_sections["t1"]]["topic_name"] == "Algebra — Section 1"
    assert by_topic[seeded_sections["t2"]]["available"] == 4
    assert by_topic[seeded_sections["t2"]]["excluded_unknown"] == 1
    # Empty sections are included with zeros, so every tab shows.
    assert by_topic[seeded_sections["t3"]]["available"] == 0
    assert by_topic[seeded_sections["t3"]]["excluded_unknown"] == 0


def test_availability_range_slice_is_bank_ordered(client, engine_db, seeded_sections):
    res = _availability(
        client,
        {
            "source_type": "topics",
            "topic_ids": [seeded_sections["t1"]],
            "question_range_start": 2,
            "question_range_end": 4,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["available"] == 3
    assert [item["number"] for item in body["sample"]] == ["2", "3", "4"]


def test_availability_range_end_beyond_pool_names_real_count(
    client, engine_db, seeded_sections
):
    res = _availability(
        client,
        {
            "source_type": "topics",
            "topic_ids": [seeded_sections["t1"]],
            "question_range_start": 1,
            "question_range_end": 99,
        },
    )
    assert res.status_code == 422, res.text
    assert "7 question(s)" in res.json()["error"]["message"]


def test_availability_range_start_after_end_is_422(client, engine_db, seeded_sections):
    res = _availability(
        client,
        {
            "source_type": "topics",
            "topic_ids": [seeded_sections["t1"]],
            "question_range_start": 4,
            "question_range_end": 2,
        },
    )
    assert res.status_code == 422


def test_availability_range_needs_single_topic(client, engine_db, seeded_sections):
    res = _availability(
        client,
        {
            "source_type": "topics",
            "topic_ids": [seeded_sections["t1"], seeded_sections["t2"]],
            "question_range_start": 1,
            "question_range_end": 2,
        },
    )
    assert res.status_code == 422
    res = _availability(
        client,
        {
            "source_type": "subjects",
            "subject_ids": [seeded_sections["subject"]],
            "question_range_start": 1,
            "question_range_end": 2,
        },
    )
    assert res.status_code == 422


def test_pool_order_is_section_then_number(client, engine_db, seeded_sections):
    # Without section-aware ordering the sample would interleave
    # (s1 Q1, s2 Q1, s1 Q2, s2 Q2, s1 Q3) — numbers 1,1,2,2,3.
    res = _availability(
        client,
        {
            "source_type": "topics",
            "topic_ids": [seeded_sections["t1"], seeded_sections["t2"]],
        },
    )
    assert res.status_code == 200, res.text
    sample = res.json()["sample"]
    assert [item["number"] for item in sample] == ["1", "2", "3", "4", "5"]
    assert all("s1 question" in item["text"] for item in sample)


# ---------------------------------------------------------------------------
# Create with a range
# ---------------------------------------------------------------------------


def test_create_test_range_valid_picks_only_from_range(
    client, engine_db, seeded_sections
):
    res = _create(
        client,
        {
            "name": "Algebra s1 Q2-Q4",
            "question_count": 3,
            "source_type": "topics",
            "source_ids": [seeded_sections["t1"]],
            "question_range_start": 2,
            "question_range_end": 4,
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["question_count"] == 3
    assert body["source_type"] == "topics"
    picked = {snap["question_text"] for snap in body["snapshots"]}
    assert picked == {
        "Algebra s1 question 2",
        "Algebra s1 question 3",
        "Algebra s1 question 4",
    }


def test_create_test_range_count_exceeds_range_is_422(client, engine_db, seeded_sections):
    res = _create(
        client,
        {
            "name": "Too many",
            "question_count": 3,
            "source_type": "topics",
            "source_ids": [seeded_sections["t1"]],
            "question_range_start": 2,
            "question_range_end": 3,
        },
    )
    assert res.status_code == 422, res.text
    assert "Only 2 question(s)" in res.json()["error"]["message"]


def test_create_test_range_end_beyond_pool_is_422(client, engine_db, seeded_sections):
    res = _create(
        client,
        {
            "name": "Beyond",
            "question_count": 1,
            "source_type": "topics",
            "source_ids": [seeded_sections["t1"]],
            "question_range_start": 1,
            "question_range_end": 99,
        },
    )
    assert res.status_code == 422, res.text
    assert "7 question(s)" in res.json()["error"]["message"]


def test_create_test_range_rejects_explicit_and_multi_topic(
    client, engine_db, seeded_sections
):
    res = _create(
        client,
        {
            "name": "Explicit range",
            "question_count": 1,
            "source_type": "explicit",
            "source_ids": [seeded_sections["t1"]],
            "question_range_start": 1,
            "question_range_end": 2,
        },
    )
    assert res.status_code == 422
    res = _create(
        client,
        {
            "name": "Multi range",
            "question_count": 1,
            "source_type": "topics",
            "source_ids": [seeded_sections["t1"], seeded_sections["t2"]],
            "question_range_start": 1,
            "question_range_end": 2,
        },
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Reading mode endpoint
# ---------------------------------------------------------------------------


def test_section_reading_returns_bank_order_with_answers_and_explanations(
    client, engine_db, seeded_sections
):
    res = client.get(
        "/api/v1/tests/sections/questions",
        params={"topic_ids": [seeded_sections["t1"]], "limit": 20, "offset": 0},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 7
    assert [q["number"] for q in body["questions"]] == ["1", "2", "3", "4", "5", "6", "7"]
    first = body["questions"][0]
    assert first["options"] == ["A1", "B1", "C1", "D1"]
    assert first["correct_index"] == 0
    assert first["correct_letter"] == "A"
    assert first["explanation"] == "Because 1 + 1 = 2, as shown in the worked solution."
    # No stored explanation anywhere else — None, never invented.
    assert all(q["explanation"] is None for q in body["questions"][1:])
    # Pagination slices the bank order.
    res = client.get(
        "/api/v1/tests/sections/questions",
        params={"topic_ids": [seeded_sections["t1"]], "limit": 2, "offset": 2},
        headers=auth_headers("token-user-a"),
    )
    assert [q["number"] for q in res.json()["questions"]] == ["3", "4"]
    # Unknown questions are excluded, like the test pool.
    res = client.get(
        "/api/v1/tests/sections/questions",
        params={"topic_ids": [seeded_sections["t2"]], "limit": 20, "offset": 0},
        headers=auth_headers("token-user-a"),
    )
    assert res.json()["total"] == 4


def test_section_reading_shared_bank_visible_to_student(
    client, engine_db, seeded_sections
):
    # USER_B sees only the shared bank questions in Section 1 —
    # USER_A's private questions never appear.
    res = client.get(
        "/api/v1/tests/sections/questions",
        params={"topic_ids": [seeded_sections["t1"]], "limit": 20, "offset": 0},
        headers=auth_headers("token-user-b"),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 2
    assert {q["text"] for q in body["questions"]} == {
        "Shared algebra question 1",
        "Shared algebra question 2",
    }
    # Section 2 holds only USER_A's private questions: empty for B.
    res = client.get(
        "/api/v1/tests/sections/questions",
        params={"topic_ids": [seeded_sections["t2"]], "limit": 20, "offset": 0},
        headers=auth_headers("token-user-b"),
    )
    assert res.json()["total"] == 0


def test_section_reading_bad_topic_and_missing_ids(client, engine_db, seeded_sections):
    res = client.get(
        "/api/v1/tests/sections/questions",
        params={"topic_ids": [str(uuid.uuid4())]},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 404
    res = client.get(
        "/api/v1/tests/sections/questions",
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 422


def test_question_item_carries_stored_explanation(client, engine_db, seeded_sections):
    res = client.get("/api/v1/questions", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    by_text = {q["text"]: q for q in res.json()["questions"]}
    assert (
        by_text["Algebra s1 question 1"]["explanation"]
        == "Because 1 + 1 = 2, as shown in the worked solution."
    )
    assert by_text["Algebra s1 question 2"]["explanation"] is None
