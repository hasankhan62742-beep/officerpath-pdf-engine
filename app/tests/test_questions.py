# OfficerPath AI — PDF Engine (Phase 2, M5)
# Question bank + results reads (GAP-3), subjects (GAP-4),
# corrections audit listing.
#
# Fixtures persist a real matched document through the Phase 1
# store (persist_matched_document) — the same rows the worker
# writes — then exercise the new read APIs against them.

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import models as db
from app.db.models import Base
from app.pipeline.matching.models import MatchedDocument, ResolvedMCQ
from app.pipeline.matching.store import persist_matched_document
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


def test_document_questions_counts_order_and_unknown(client, engine_db, seeded_doc):
    doc_id, by_number = seeded_doc
    res = client.get(f"/api/v1/documents/{doc_id}/questions", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 4  # 3 questions + 1 pending row
    assert body["counts"] == {
        "questions": 4,
        "answered": 2,
        "unknown": 2,  # Q2 unknown + Q3 pending (no answer row)
        "pending": 1,
        "inferred": 1,
        "corrected": 0,
    }
    assert body["qa_pairs"] == 1  # counted only, never a fake question row
    numbers = [q["number"] for q in body["questions"]]
    assert numbers == ["1", "2", "3", "4"]  # printed-number order, not created_at
    q2 = next(q for q in body["questions"] if q["number"] == "2")
    assert q2["correct_index"] == -1
    assert q2["correct_letter"] == ""
    assert q2["confidence"] is None
    assert q2["answer_status"] == "unknown"
    q4 = next(q for q in body["questions"] if q["number"] == "4")
    assert q4["inferred"] is True
    assert q4["answer_status"] == "detected"  # inferred is never "verified"
    assert q4["verified"] is False
    q3 = next(q for q in body["questions"] if q["number"] == "3")
    assert q3["answer_status"] == "needs_review"
    assert q3["status"] == "pending"


def test_document_questions_pagination_matches_full_read(client, engine_db, seeded_doc):
    """Bug (b)'s fix, same endpoint: pages slice the same
    printed-number order and carry the same counts/total as the
    full read — pagination must never change what a page holds."""
    doc_id, _ = seeded_doc
    base = f"/api/v1/documents/{doc_id}/questions"
    full = client.get(base, headers=auth_headers("token-user-a")).json()
    assert full["total"] == 4
    page1 = client.get(f"{base}?limit=2&offset=0", headers=auth_headers("token-user-a")).json()
    page2 = client.get(f"{base}?limit=2&offset=2", headers=auth_headers("token-user-a")).json()
    assert [q["number"] for q in page1["questions"]] == ["1", "2"]
    assert [q["number"] for q in page2["questions"]] == ["3", "4"]
    assert page1["questions"] + page2["questions"] == full["questions"]
    assert page1["counts"] == full["counts"]
    assert page2["counts"] == full["counts"]
    assert page1["total"] == full["total"] == 4
    assert page1["qa_pairs"] == full["qa_pairs"] == 1
    # Past the end: an empty page, still with the real counts.
    empty = client.get(f"{base}?limit=2&offset=10", headers=auth_headers("token-user-a")).json()
    assert empty["questions"] == []
    assert empty["total"] == 4
    assert empty["counts"] == full["counts"]


def test_read_path_indexes_exist_in_models():
    """Bug (a)/(b) root cause, pinned in the model metadata:
    the read paths seq-scanned question_options and
    extracted_answers because no index keyed them by
    question_id, and question_subjects had no topic index for
    the counts query. The migration must create these exact
    names (023_read_indexes)."""
    assert "ix_question_options_question" in {
        idx.name for idx in db.QuestionOption.__table__.indexes
    }
    assert "ix_extracted_answers_question_created" in {
        idx.name for idx in db.ExtractedAnswer.__table__.indexes
    }
    assert "ix_question_subjects_topic" in {
        idx.name for idx in db.QuestionSubject.__table__.indexes
    }


def test_question_detail_has_evidence_trail(client, engine_db, seeded_doc):
    _, by_number = seeded_doc
    res = client.get(f"/api/v1/questions/{by_number['1']}", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["correct_index"] == 1
    assert body["correct_letter"] == "B"
    assert body["answer_status"] == "verified"
    assert body["verified"] is True
    assert body["answer_source"] == "trailing-key"
    assert len(body["evidence"]) == 1
    ev = body["evidence"][0]
    assert ev["detector"] == "trailing-key"
    assert ev["value_normalized"] == "B"
    assert ev["artifact_ref"] == "key entry 1 -> (B)"
    assert body["corrections"] == []


def test_bank_filters_and_search(client, engine_db, seeded_doc):
    doc_id, _ = seeded_doc
    base = "/api/v1/questions"
    res = client.get(base, headers=auth_headers("token-user-a"))
    assert res.json()["total"] == 4
    res = client.get(f"{base}?status=answered", headers=auth_headers("token-user-a"))
    assert res.json()["total"] == 2
    res = client.get(f"{base}?status=unknown", headers=auth_headers("token-user-a"))
    assert res.json()["total"] == 2
    res = client.get(f"{base}?status=pending", headers=auth_headers("token-user-a"))
    assert res.json()["total"] == 1
    res = client.get(f"{base}?status=inferred", headers=auth_headers("token-user-a"))
    assert res.json()["total"] == 1
    res = client.get(f"{base}?status=corrected", headers=auth_headers("token-user-a"))
    assert res.json()["total"] == 0
    res = client.get(f"{base}?q=capital", headers=auth_headers("token-user-a"))
    assert res.json()["total"] == 1
    res = client.get(f"{base}?q=multan", headers=auth_headers("token-user-a"))
    assert res.json()["total"] == 1
    res = client.get(f"{base}?document_id={doc_id}", headers=auth_headers("token-user-a"))
    assert res.json()["total"] == 4
    res = client.get(f"{base}?confidence_min=0.9", headers=auth_headers("token-user-a"))
    assert res.json()["total"] == 1  # only the 1.0 trailing-key answer
    res = client.get(
        f"{base}?confidence_min=0.5&confidence_max=0.7",
        headers=auth_headers("token-user-a"),
    )
    assert res.json()["total"] == 1  # only the 0.62 inferred answer
    res = client.get(f"{base}?status=bogus", headers=auth_headers("token-user-a"))
    assert res.status_code == 422
    # Pagination: limit slices, total stays whole.
    res = client.get(f"{base}?limit=2&offset=2", headers=auth_headers("token-user-a"))
    assert res.json()["total"] == 4
    assert len(res.json()["questions"]) == 2


def test_bank_is_per_user(client, engine_db, seeded_doc):
    _, by_number = seeded_doc
    res = client.get("/api/v1/questions", headers=auth_headers("token-user-b"))
    assert res.json()["total"] == 0
    res = client.get(f"/api/v1/questions/{by_number['1']}", headers=auth_headers("token-user-b"))
    assert res.status_code == 404
    res = client.get(
        f"/api/v1/documents/{seeded_doc[0]}/questions",
        headers=auth_headers("token-user-b"),
    )
    assert res.status_code == 404


def test_correction_round_trip_and_audit(client, engine_db, seeded_doc):
    doc_id, by_number = seeded_doc
    q2 = by_number["2"]
    # Correct the unknown answer to C.
    res = client.post(
        f"/api/v1/documents/{doc_id}/questions/{q2}/corrections",
        json={"field": "answer", "new_value": "C", "reason": "checked against key"},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    assert res.json()["new_value"] == "C"
    assert res.json()["old_value"] is None
    # The detail now shows the corrected answer + flag.
    res = client.get(f"/api/v1/questions/{q2}", headers=auth_headers("token-user-a"))
    body = res.json()
    assert body["correct_index"] == 2
    assert body["correct_letter"] == "C"
    assert body["corrected"] is True
    assert body["answer_status"] == "verified"  # manual is the top of precedence
    assert body["answer_source"] == "manual"
    assert len(body["corrections"]) == 1
    entry = body["corrections"][0]
    assert entry["field_name"] == "answer"
    assert entry["old_value"] is None
    assert entry["new_value"] == "C"
    assert entry["reason"] == "checked against key"
    # The standalone audit listing agrees.
    res = client.get(
        f"/api/v1/documents/{doc_id}/questions/{q2}/corrections",
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200
    assert res.json()["total"] == 1
    # The bank's corrected filter now finds it.
    res = client.get("/api/v1/questions?status=corrected", headers=auth_headers("token-user-a"))
    assert res.json()["total"] == 1
    # Another user cannot correct or read the audit trail.
    res = client.post(
        f"/api/v1/documents/{doc_id}/questions/{q2}/corrections",
        json={"field": "answer", "new_value": "A", "reason": "x"},
        headers=auth_headers("token-user-b"),
    )
    assert res.status_code == 404


def test_subjects_assign_unassign(client, engine_db, seeded_doc):
    _, by_number = seeded_doc
    factory = engine_db
    session = factory()
    subject = db.Subject(name="General Knowledge", slug="general-knowledge")
    session.add(subject)
    session.commit()
    subject_id = str(subject.id)
    session.close()
    res = client.get("/api/v1/subjects", headers=auth_headers("token-user-a"))
    assert res.status_code == 200
    assert res.json()["total"] == 1
    assert res.json()["subjects"][0]["slug"] == "general-knowledge"
    q1 = by_number["1"]
    res = client.post(
        f"/api/v1/questions/{q1}/subjects",
        json={"subject_id": subject_id},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    assert res.json()["already_assigned"] is False
    assert res.json()["subject_slug"] == "general-knowledge"
    # Idempotent re-assign.
    res = client.post(
        f"/api/v1/questions/{q1}/subjects",
        json={"subject_id": subject_id},
        headers=auth_headers("token-user-a"),
    )
    assert res.json()["already_assigned"] is True
    # The bank filter and the detail both show the assignment.
    res = client.get(
        f"/api/v1/questions?subject_id={subject_id}", headers=auth_headers("token-user-a")
    )
    assert res.json()["total"] == 1
    res = client.get(f"/api/v1/questions/{q1}", headers=auth_headers("token-user-a"))
    assert res.json()["subjects"][0]["subject_slug"] == "general-knowledge"
    # Unassign, then the filter finds nothing.
    res = client.delete(
        f"/api/v1/questions/{q1}/subjects/{subject_id}",
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200
    assert res.json()["removed"] is True
    res = client.get(
        f"/api/v1/questions?subject_id={subject_id}", headers=auth_headers("token-user-a")
    )
    assert res.json()["total"] == 0
    # Unknown subject and other-user question are 404s.
    res = client.post(
        f"/api/v1/questions/{q1}/subjects",
        json={"subject_id": str(uuid.uuid4())},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 404
    res = client.post(
        f"/api/v1/questions/{q1}/subjects",
        json={"subject_id": subject_id},
        headers=auth_headers("token-user-b"),
    )
    assert res.status_code == 404


def test_migration_0005_seeds_13_subjects(tmp_path, monkeypatch):
    """M5: a database built ONLY by `alembic upgrade head` carries
    the 13 seeded subjects (doc 03 §2.2), and the downgrade
    refuses while user assignments exist."""
    from alembic.config import Config

    from alembic import command
    from app.config import settings
    from app.db.models import Document, Job

    db_file = tmp_path / "alembic-m5.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_file}")
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine, tables=[Document.__table__, Job.__table__])
    engine.dispose()

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_file}")
    try:
        with Session(engine) as session:
            rows = session.query(db.Subject).order_by(db.Subject.slug).all()
            assert len(rows) == 13
            slugs = [row.slug for row in rows]
            assert "general-knowledge" in slugs
            assert "pakistan-affairs" in slugs
            assert "computer-science" in slugs
            assert "general-ability" in slugs
            # Regression (M5 E2E find): a migration-seeded subject must
            # be findable by the ORM id filter the assign path uses.
            # The seed used to insert dashed UUID strings while sa.Uuid
            # stores 32-char hex on SQLite, so assign_subject 404'd
            # "Subject not found" for a subject the list endpoint
            # returned. The list + id-lookup round-trip must agree.
            from app.services import questions as question_service

            listed = question_service.list_subjects(session)
            assert listed["total"] == 13
            first = listed["subjects"][0]
            found = (
                session.query(db.Subject).filter(db.Subject.id == uuid.UUID(first["id"])).first()
            )
            assert found is not None, "seeded subject not findable by ORM id filter"
            assert found.slug == first["slug"]
        # Downgrade is clean while no user assignments exist.
        # (The session is closed first: an open SQLite read
        # transaction would block Alembic's DDL.)
        command.downgrade(cfg, "0004_m4_profile_timestamps")
        from sqlalchemy import inspect as sa_inspect

        assert sa_inspect(engine).has_table("subjects") is False
        # Re-upgrade, add one assignment, downgrade must refuse.
        command.upgrade(cfg, "head")
        with Session(engine) as session:
            subject = session.query(db.Subject).first()
            assert subject is not None
            session.add(
                db.QuestionSubject(
                    question_id=uuid.uuid4(),
                    subject_id=subject.id,
                    topic_id=None,
                    assigned_by=uuid.uuid4(),
                    confidence="manual",
                )
            )
            session.commit()
        with pytest.raises(RuntimeError, match="Refusing downgrade"):
            command.downgrade(cfg, "0004_m4_profile_timestamps")
    finally:
        engine.dispose()
