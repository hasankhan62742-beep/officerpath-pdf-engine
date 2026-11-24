# OfficerPath AI — Phase 2, M12
# Performance regression tests (the live 53s availability fix).
#
# LIVE EVIDENCE (2026-11-24, Render logs): GET
# /tests/availability for source "all" took ~53s per call —
# the old pool resolution materialised all 52,573
# ExtractedQuestion ORM objects plus every option and answer
# row, starving the 5s health check until Render restarted
# the instance. The fix resolves the pool as plain tuples
# from four small queries (candidate columns, option holders,
# latest answer labels, topic assignments) classified + sorted
# in Python — full rows only for the picked questions /
# 5-row sample. No per-row subqueries, no new indexes needed.
#
# These tests pin the new shape on a 1,500-question pool:
# exact counts (classification must match the old Python
# code row for row), the sample in bank order, and a bound on
# the number of SQL statements per call — the old code's cost
# was row volume, and the statement bound guards the
# N+1-shaped regressions that would bring it back. Wall-time
# is reported by pytest --durations; a local SQLite timing
# cannot reproduce the 53s Render-free figure, so the timing
# bound here is a generous smoke guard only. Measured locally
# (1,580-row pool, SQLite): availability "all" 8 statements
# ~0.18s, topics breakdown ~0.20s, create (100 questions)
# 14 SELECTs ~0.12s, reading page ~0.28s for two pages.

import time
import uuid

import pytest
from sqlalchemy import event

from app.db import models as db
from app.tests.conftest import USER_A, USER_ADMIN, auth_headers
from app.tests.test_tests_range import _seed_doc

AVAILABLE = 1500
UNKNOWN = 50
NO_OPTIONS = 30


@pytest.fixture()
def large_bank(engine_db):
    """USER_A private doc: 1,200 known + 50 unknown questions
    (Algebra Section 1, numbers 1-1250) + 30 no-option
    questions (numbers 1251-1280). USER_ADMIN shared doc: 300
    known questions (Section 1, numbers 1-300). All assigned
    to topic Algebra — Section 1; Section 2 stays empty."""
    factory = engine_db
    session = factory()
    subject = db.Subject(name="Mathematics", slug="mathematics")
    session.add(subject)
    session.flush()
    t1 = db.Topic(subject_id=subject.id, name="Algebra — Section 1", slug="algebra-s1")
    t2 = db.Topic(subject_id=subject.id, name="Algebra — Section 2", slug="algebra-s2")
    session.add_all([t1, t2])
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

    doc_a, _ = _seed_doc(
        session,
        USER_A,
        "Perf Paper A",
        [(n, f"Perf question {n}", n % 4) for n in range(1, 1201)]
        + [(n, f"Perf unknown question {n}", -1) for n in range(1201, 1251)],
        content_hash="f" * 64,
    )
    _assign(doc_a, t1)
    doc_b, _ = _seed_doc(
        session,
        USER_ADMIN,
        "Perf Shared Bank",
        [(n, f"Shared perf question {n}", n % 4) for n in range(1, 301)],
        is_shared=True,
        content_hash="0" * 64,
    )
    _assign(doc_b, t1)
    no_option_ids = []
    for n in range(1251, 1281):
        qid = uuid.uuid4()
        no_option_ids.append(qid)
        session.add(
            db.ExtractedQuestion(
                id=qid,
                document_id=doc_a,
                question_number=str(n),
                normalized_text=f"Perf no-option question {n}",
                original_text=f"Perf no-option question {n}",
                validation_status="answered",
                source_pages=[1],
            )
        )
    session.flush()
    for qid in no_option_ids:
        session.add(
            db.QuestionSubject(
                question_id=qid,
                subject_id=subject.id,
                topic_id=t1.id,
                assigned_by=uuid.UUID(USER_A),
            )
        )
    session.commit()
    out = {
        "engine": factory.kw["bind"],
        "subject": str(subject.id),
        "t1": str(t1.id),
        "t2": str(t2.id),
        "doc_a": str(doc_a),
        "doc_b": str(doc_b),
    }
    session.close()
    return out


class _StatementCounter:
    """Counts every SQL statement run on the engine while the
    context is open (SELECTs and writes alike)."""

    def __init__(self, engine):
        self.engine = engine
        self.statements: list[str] = []

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._count)
        return self

    def __exit__(self, *exc):
        event.remove(self.engine, "before_cursor_execute", self._count)
        return False

    def _count(self, conn, cursor, statement, parameters, context, executemany):
        self.statements.append(statement)

    def selects(self):
        return [s for s in self.statements if s.strip().upper().startswith("SELECT")]


def _availability(client, params):
    return client.get(
        "/api/v1/tests/availability", params=params, headers=auth_headers("token-user-a")
    )


def test_availability_all_large_pool_counts_and_sample(client, large_bank):
    res = _availability(client, {"source_type": "all"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["available"] == AVAILABLE
    assert body["excluded_unknown"] == UNKNOWN
    assert body["excluded_no_options"] == NO_OPTIONS
    # Sample = first 5 in bank order: Section 1, then number,
    # then document — both docs hold numbers 1-300, so the
    # first five are 1, 1, 2, 2, 3.
    assert len(body["sample"]) == 5
    assert [s["number"] for s in body["sample"]] == ["1", "1", "2", "2", "3"]
    for item in body["sample"]:
        assert item["correct_index"] in (0, 1, 2, 3)


def test_availability_all_large_pool_statement_bound(client, large_bank):
    with _StatementCounter(large_bank["engine"]) as counter:
        started = time.perf_counter()
        res = _availability(client, {"source_type": "all"})
        elapsed = time.perf_counter() - started
    assert res.status_code == 200, res.text
    # One aggregate count + one topics load + one ID-only pool
    # query + sample rows/answers/titles: a handful of small
    # statements. The old path issued the same count of
    # statements but returned 52k+ rows through them; the
    # count bound here guards the N+1 shape, the exact-count
    # test above guards the classification.
    assert len(counter.statements) <= 25, counter.statements
    assert elapsed < 10


def test_availability_topics_breakdown_large_pool(client, large_bank):
    res = _availability(
        client,
        {
            "source_type": "topics",
            "topic_ids": [large_bank["t1"], large_bank["t2"]],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["available"] == AVAILABLE
    by_topic = {row["topic_id"]: row for row in body["by_topic"]}
    s1 = by_topic[large_bank["t1"]]
    assert s1["available"] == AVAILABLE
    assert s1["excluded_unknown"] == UNKNOWN
    assert s1["excluded_no_options"] == NO_OPTIONS
    s2 = by_topic[large_bank["t2"]]
    assert s2["available"] == 0
    assert s2["excluded_unknown"] == 0
    assert s2["excluded_no_options"] == 0


def test_create_test_from_all_large_pool(client, large_bank):
    with _StatementCounter(large_bank["engine"]) as counter:
        started = time.perf_counter()
        res = client.post(
            "/api/v1/tests",
            json={
                "name": "Perf Test",
                "question_count": 100,
                "source_type": "all",
            },
            headers=auth_headers("token-user-a"),
        )
        elapsed = time.perf_counter() - started
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["question_count"] == 100
    assert len(body["snapshots"]) == 100
    assert body["excluded_unknown"] == UNKNOWN
    assert body["excluded_no_options"] == NO_OPTIONS
    question_ids = [s["question_id"] for s in body["snapshots"]]
    assert len(set(question_ids)) == 100  # no duplicates
    for snap in body["snapshots"]:
        assert snap["is_unknown"] is False
        assert snap["correct_index"] is None  # key withheld until submit
        assert len(snap["options"]) == 4
        assert snap["question_text"].startswith(("Perf question", "Shared perf question"))
    # The pool queries are a handful of SELECTs; the ~100
    # snapshot INSERTs are expected and unbounded here.
    assert len(counter.selects()) <= 15, counter.selects()
    assert elapsed < 10


def test_reading_large_section_paginates_in_bank_order(client, large_bank):
    res = client.get(
        "/api/v1/tests/sections/questions",
        params={"topic_ids": [large_bank["t1"]], "limit": 10, "offset": 0},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == AVAILABLE
    assert len(body["questions"]) == 10
    assert [q["number"] for q in body["questions"]] == [
        "1", "1", "2", "2", "3", "3", "4", "4", "5", "5",
    ]
    res = client.get(
        "/api/v1/tests/sections/questions",
        params={"topic_ids": [large_bank["t1"]], "limit": 10, "offset": 100},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == AVAILABLE
    assert [q["number"] for q in body["questions"]] == [
        "51", "51", "52", "52", "53", "53", "54", "54", "55", "55",
    ]
    for q in body["questions"]:
        assert q["correct_index"] in (0, 1, 2, 3)
        assert len(q["options"]) == 4
