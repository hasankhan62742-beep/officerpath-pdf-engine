# OfficerPath AI — Phase 2, M11
# Shared question bank: students build tests from admin-shared
# bank documents; private documents stay private.
#
# Seed: three documents, each with 2 answered questions —
#   * admin bank doc (USER_ADMIN), is_shared=True
#   * USER_B private doc (is_shared left unset — the default)
#   * USER_A own doc (is_shared left unset — the default)
# The admin doc's questions are assigned to subject General
# Knowledge, so the subjects source can find them. USER_B's
# questions have no subject assignment (a private document
# must never leak through a shared subject either).

import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import models as db
from app.pipeline.matching.models import MatchedDocument, ResolvedMCQ
from app.pipeline.matching.store import persist_matched_document
from app.tests.conftest import USER_A, USER_ADMIN, USER_B, auth_headers


def _matched(questions):
    """questions: list of (number, text, options, correct_index)."""
    return MatchedDocument(
        questions=[
            ResolvedMCQ(
                number=number,
                text=text,
                options=options,
                correct_index=correct_index,
                answer_source="trailing-key",
                confidence=1.0,
                raw_confidence=1.0,
                verified=True,
                status="answered",
                page=1,
                paper="Paper 66",
            )
            for number, text, options, correct_index in questions
        ],
        qa_pairs=[],
        pending=[],
        counts={
            "questions": len(questions),
            "answered": len(questions),
            "unknown": 0,
            "pending": 0,
        },
    )


def _seed_doc(session, owner, title, questions, is_shared=None):
    """Persist one document + job + matched questions. Returns
    (document_id, question_ids by number). ``is_shared`` is only
    set when given, so the default (False) is exercised by the
    private documents."""
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
        content_hash="b" * 64,
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
    by_number = {row.question_number: str(row.id) for row in rows}
    return doc_id, by_number


@pytest.fixture()
def seeded_bank(engine_db):
    """Admin shared bank doc + USER_B private doc + USER_A own
    doc, each with 2 answered questions. The shared questions
    are assigned to General Knowledge. Returns ids."""
    factory = engine_db
    session = factory()
    admin_doc, admin_qs = _seed_doc(
        session,
        USER_ADMIN,
        "ExamVeda Bank — Computer",
        [
            (
                1,
                "What is the capital of Pakistan?",
                ["Karachi", "Islamabad", "Lahore", "Quetta"],
                1,
            ),
            (
                2,
                "Which river flows through Multan?",
                ["Indus", "Chenab", "Ravi", "Jhelum"],
                0,
            ),
        ],
        is_shared=True,
    )
    user_b_doc, user_b_qs = _seed_doc(
        session,
        USER_B,
        "Private Paper",
        [
            (1, "What is 2 + 2?", ["3", "4", "5", "6"], 1),
            (2, "What is 3 + 3?", ["5", "6", "7", "8"], 1),
        ],
    )
    user_a_doc, user_a_qs = _seed_doc(
        session,
        USER_A,
        "My Paper",
        [
            (1, "Which ocean is the largest?", ["Atlantic", "Indian", "Pacific", "Arctic"], 2),
            (2, "Which planet is the Red Planet?", ["Venus", "Mars", "Jupiter", "Saturn"], 1),
        ],
    )
    gk = db.Subject(name="General Knowledge", slug="general-knowledge")
    session.add(gk)
    session.flush()
    admin_rows = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.document_id == admin_doc)
        .all()
    )
    for row in admin_rows:
        session.add(
            db.QuestionSubject(
                question_id=row.id,
                subject_id=gk.id,
                topic_id=None,
                assigned_by=uuid.UUID(USER_ADMIN),
            )
        )
    session.commit()
    gk_id = str(gk.id)
    session.close()
    return {
        "admin_doc": str(admin_doc),
        "admin_qs": admin_qs,
        "user_b_doc": str(user_b_doc),
        "user_b_qs": user_b_qs,
        "user_a_doc": str(user_a_doc),
        "user_a_qs": user_a_qs,
        "gk": gk_id,
    }


def _create(client, payload, token="token-user-a"):
    return client.post("/api/v1/tests", json=payload, headers=auth_headers(token))


def _availability(client, params, token="token-user-a"):
    return client.get("/api/v1/tests/availability", params=params, headers=auth_headers(token))


# ---------------------------------------------------------------------------
# (a) Student builds a test from the shared bank via subjects
# ---------------------------------------------------------------------------


def test_student_builds_test_from_shared_bank_via_subjects(client, engine_db, seeded_bank):
    res = _availability(client, {"source_type": "subjects", "subject_ids": [seeded_bank["gk"]]})
    assert res.status_code == 200, res.text
    assert res.json()["available"] == 2
    res = _create(
        client,
        {
            "name": "Shared Bank Practice",
            "question_count": 2,
            "source_type": "subjects",
            "source_ids": [seeded_bank["gk"]],
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert len(body["snapshots"]) == 2
    snapshot_qids = {s["question_id"] for s in body["snapshots"]}
    assert snapshot_qids == set(seeded_bank["admin_qs"].values())


def test_student_builds_test_from_shared_bank_via_documents(client, engine_db, seeded_bank):
    res = _create(
        client,
        {
            "name": "Shared Bank Docs",
            "question_count": 2,
            "source_type": "documents",
            "source_ids": [seeded_bank["admin_doc"]],
        },
    )
    assert res.status_code == 201, res.text
    snapshot_qids = {s["question_id"] for s in res.json()["snapshots"]}
    assert snapshot_qids == set(seeded_bank["admin_qs"].values())


def test_student_builds_test_from_shared_bank_via_all(client, engine_db, seeded_bank):
    # Pool for USER_A: own 2 + shared 2. USER_B's private 2 are excluded.
    res = _availability(client, {"source_type": "all"})
    assert res.status_code == 200, res.text
    assert res.json()["available"] == 4


# ---------------------------------------------------------------------------
# (b) Another student's private document stays unreachable
# ---------------------------------------------------------------------------


def test_student_cannot_build_from_another_students_private_document(
    client, engine_db, seeded_bank
):
    res = _create(
        client,
        {
            "name": "Snooping",
            "question_count": 2,
            "source_type": "documents",
            "source_ids": [seeded_bank["user_b_doc"]],
        },
    )
    assert res.status_code == 404, res.text
    res = _create(
        client,
        {
            "name": "Snooping Mixed",
            "question_count": 2,
            "source_type": "mixed",
            "source_ids": {
                "document_ids": [seeded_bank["user_b_doc"]],
                "subject_ids": [],
            },
        },
    )
    assert res.status_code == 404, res.text


def test_explicit_pick_from_another_students_private_question_is_404(
    client, engine_db, seeded_bank
):
    qid = next(iter(seeded_bank["user_b_qs"].values()))
    res = _create(
        client,
        {
            "name": "Snooping Explicit",
            "question_count": 1,
            "source_type": "explicit",
            "source_ids": [qid],
        },
    )
    assert res.status_code == 404, res.text


# ---------------------------------------------------------------------------
# (c) The student's own documents still work as before
# ---------------------------------------------------------------------------


def test_student_own_documents_still_work(client, engine_db, seeded_bank):
    res = _create(
        client,
        {
            "name": "My Own Paper",
            "question_count": 2,
            "source_type": "documents",
            "source_ids": [seeded_bank["user_a_doc"]],
        },
    )
    assert res.status_code == 201, res.text
    snapshot_qids = {s["question_id"] for s in res.json()["snapshots"]}
    assert snapshot_qids == set(seeded_bank["user_a_qs"].values())


def test_explicit_pick_from_shared_bank_works(client, engine_db, seeded_bank):
    qids = list(seeded_bank["admin_qs"].values())
    res = _create(
        client,
        {
            "name": "Shared Explicit",
            "question_count": 2,
            "source_type": "explicit",
            "source_ids": qids,
        },
    )
    assert res.status_code == 201, res.text
    snapshot_qids = {s["question_id"] for s in res.json()["snapshots"]}
    assert snapshot_qids == set(qids)


# ---------------------------------------------------------------------------
# (d) is_shared defaults to False
# ---------------------------------------------------------------------------


def test_is_shared_defaults_false(client, engine_db, seeded_bank):
    factory = engine_db
    session = factory()
    try:
        for doc_id in (seeded_bank["user_b_doc"], seeded_bank["user_a_doc"]):
            row = session.query(db.Document).filter(db.Document.id == uuid.UUID(doc_id)).first()
            assert row is not None
            assert row.is_shared is False
        admin = (
            session.query(db.Document)
            .filter(db.Document.id == uuid.UUID(seeded_bank["admin_doc"]))
            .first()
        )
        assert admin.is_shared is True
    finally:
        session.close()


# ---------------------------------------------------------------------------
# (e) Unsharing removes the questions from the student pool
# ---------------------------------------------------------------------------


def test_unsharing_removes_shared_questions_from_pool(client, engine_db, seeded_bank):
    res = client.patch(
        f"/api/v1/admin/documents/{seeded_bank['admin_doc']}/sharing",
        json={"is_shared": False},
        headers=auth_headers("token-admin"),
    )
    assert res.status_code == 200, res.text
    assert res.json()["is_shared"] is False
    assert res.json()["id"] == seeded_bank["admin_doc"]
    res = _availability(client, {"source_type": "subjects", "subject_ids": [seeded_bank["gk"]]})
    assert res.status_code == 200, res.text
    assert res.json()["available"] == 0
    res = _create(
        client,
        {
            "name": "After Unshare",
            "question_count": 1,
            "source_type": "subjects",
            "source_ids": [seeded_bank["gk"]],
        },
    )
    assert res.status_code == 422, res.text
    # Re-sharing restores the pool at once.
    res = client.patch(
        f"/api/v1/admin/documents/{seeded_bank['admin_doc']}/sharing",
        json={"is_shared": True},
        headers=auth_headers("token-admin"),
    )
    assert res.status_code == 200, res.text
    assert res.json()["is_shared"] is True
    res = _availability(client, {"source_type": "subjects", "subject_ids": [seeded_bank["gk"]]})
    assert res.json()["available"] == 2


def test_non_admin_cannot_toggle_sharing(client, engine_db, seeded_bank):
    res = client.patch(
        f"/api/v1/admin/documents/{seeded_bank['admin_doc']}/sharing",
        json={"is_shared": False},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 404, res.text
    # The flag is untouched by the denied attempt.
    factory = engine_db
    session = factory()
    try:
        row = (
            session.query(db.Document)
            .filter(db.Document.id == uuid.UUID(seeded_bank["admin_doc"]))
            .first()
        )
        assert row.is_shared is True
    finally:
        session.close()


def test_sharing_unknown_document_is_404(client, engine_db, seeded_bank):
    res = client.patch(
        f"/api/v1/admin/documents/{uuid.uuid4()}/sharing",
        json={"is_shared": True},
        headers=auth_headers("token-admin"),
    )
    assert res.status_code == 404, res.text


# ---------------------------------------------------------------------------
# Documents list: shared docs visible only with include_shared
# ---------------------------------------------------------------------------


def test_documents_list_include_shared(client, engine_db, seeded_bank):
    res = client.get("/api/v1/documents", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    own = {d["id"] for d in res.json()["documents"]}
    assert seeded_bank["user_a_doc"] in own
    assert seeded_bank["admin_doc"] not in own
    assert seeded_bank["user_b_doc"] not in own
    res = client.get("/api/v1/documents?include_shared=true", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    items = {d["id"]: d for d in res.json()["documents"]}
    assert seeded_bank["admin_doc"] in items
    assert items[seeded_bank["admin_doc"]]["is_shared"] is True
    assert items[seeded_bank["user_a_doc"]]["is_shared"] is False
    # Another student's private document never appears, even shared-listed.
    assert seeded_bank["user_b_doc"] not in items


# ---------------------------------------------------------------------------
# Migration 0011 on a fresh database built only by Alembic
# ---------------------------------------------------------------------------


def test_migration_0011_fresh_db_has_is_shared_with_default_false(tmp_path, monkeypatch):
    """A database built ONLY by ``alembic upgrade head`` has the
    is_shared column with server default false; the downgrade
    removes it and the upgrade restores it."""
    from alembic.config import Config

    from alembic import command

    db_file = tmp_path / "alembic-m11.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_file}")

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_file}")
    try:
        cols = {c["name"] for c in inspect(engine).get_columns("documents")}
        assert "is_shared" in cols, f"missing after upgrade head: {sorted(cols)}"
        with Session(engine) as session:
            # Raw insert without the column: the server default applies.
            session.execute(
                text(
                    "INSERT INTO documents "
                    "(id, user_id, title, storage_path, file_type, file_size_bytes) "
                    "VALUES (:id, :user_id, :title, :path, :ftype, :size)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "user_id": str(uuid.uuid4()),
                    "title": "Migration proof",
                    "path": "m11/proof.pdf",
                    "ftype": "pdf",
                    "size": 100,
                },
            )
            session.commit()
            row = session.query(db.Document).first()
            assert row is not None
            assert row.is_shared is False
    finally:
        engine.dispose()
    command.downgrade(cfg, "0010_m10_explanations")
    engine = create_engine(f"sqlite:///{db_file}")
    try:
        cols = {c["name"] for c in inspect(engine).get_columns("documents")}
        assert "is_shared" not in cols
    finally:
        engine.dispose()
    command.upgrade(cfg, "head")
