# OfficerPath AI — Phase 2, M9
# Admin foundation (GAP-10), notifications (GAP-9), security
# hardening (headers, CORS final, cross-user tests).
#
# Admin rule under test (doc 05 §4): admin is a claim on the
# VERIFIED Supabase JWT user record (app_metadata.is_admin).
# Non-admins get 404 on every admin route (URL + API) — never a
# 403 that confirms the route exists. No request body can ever
# confer admin: an is_admin field in a body is ignored + logged.
#
# Seed: one 3-question document persisted through the Phase 1
# store (same rows the worker writes). Standard attempt answers
# Q1/Q2 correct, Q3 incorrect — so the submit writes exactly
# two notification rows (test_submitted + result_ready) and one
# mistake row, and the admin lists show real rows.

import uuid

import pytest
from sqlalchemy import create_engine

from app.config import settings
from app.db import models as db
from app.integrations.supabase_auth import verify_jwt
from app.pipeline.matching.models import MatchedDocument, ResolvedMCQ
from app.pipeline.matching.store import persist_matched_document
from app.services.notifications import create_notification
from app.tests.conftest import USER_A, USER_ADMIN, auth_headers

ADMIN_ROUTES = [
    "/api/v1/admin/overview",
    "/api/v1/admin/users",
    "/api/v1/admin/documents",
    "/api/v1/admin/jobs",
    "/api/v1/admin/errors",
    "/api/v1/admin/questions",
]


def _matched3() -> MatchedDocument:
    def q(number, text, options, correct_index, page):
        return ResolvedMCQ(
            number=number,
            text=text,
            options=options,
            correct_index=correct_index,
            answer_source="trailing-key",
            confidence=1.0,
            raw_confidence=1.0,
            verified=True,
            status="answered",
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
            q(
                2,
                "Which river flows through Multan?",
                ["Indus", "Chenab", "Ravi", "Jhelum"],
                0,
                1,
            ),
            q(
                3,
                "The largest desert of Pakistan is?",
                ["Thar", "Cholistan", "Kharan", "Thal"],
                2,
                1,
            ),
        ],
        qa_pairs=[],
        pending=[],
        counts={"questions": 3, "answered": 3, "unknown": 0, "pending": 0},
    )


@pytest.fixture()
def seeded_doc(engine_db):
    """3-question document + done job. Returns (doc_id, job_id, question_ids)."""
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
            page_count=1,
            content_hash="d" * 64,
        )
    )
    session.add(db.Job(id=job_id, user_id=uuid.UUID(USER_A), document_id=doc_id, status="done"))
    session.commit()
    persist_matched_document(session, document_id=doc_id, job_id=job_id, matched=_matched3())
    rows = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.document_id == doc_id)
        .order_by(db.ExtractedQuestion.question_number)
        .all()
    )
    out = (doc_id, job_id, [str(r.id) for r in rows])
    session.close()
    return out


def _admin_headers() -> dict:
    return auth_headers("token-admin")


def _create_profile(client, token="token-user-a", full_name="Test Student"):
    res = client.post(
        "/api/v1/me",
        json={"full_name": full_name},
        headers=auth_headers(token),
    )
    assert res.status_code in (200, 201), res.text
    return res.json()


def _submit_test(client, question_ids):
    """Explicit 3-question test, Q1/Q2 correct, Q3 incorrect."""
    res = client.post(
        "/api/v1/tests",
        json={
            "name": "M9 Test",
            "question_count": 3,
            "source_type": "explicit",
            "source_ids": question_ids,
            "include_unknown": False,
        },
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code in (200, 201), res.text
    test_id = res.json()["test_id"]
    res = client.post(f"/api/v1/tests/{test_id}/start", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    session_res = client.get(
        f"/api/v1/tests/{test_id}/session", headers=auth_headers("token-user-a")
    )
    assert session_res.status_code == 200, session_res.text
    snapshots = session_res.json()["snapshots"]
    assert len(snapshots) == 3, session_res.text
    # Map question_id -> snapshot; correct indices are Q1=1, Q2=0, Q3=2.
    by_question = {s["question_id"]: s for s in snapshots}
    answers = [
        {"snapshot_id": by_question[question_ids[0]]["snapshot_id"], "selected_index": 1},
        {"snapshot_id": by_question[question_ids[1]]["snapshot_id"], "selected_index": 0},
        # Q3 answered 0, correct is 2 — the one incorrect answer.
        {"snapshot_id": by_question[question_ids[2]]["snapshot_id"], "selected_index": 0},
    ]
    res = client.post(
        f"/api/v1/tests/{test_id}/answers",
        json={"answers": answers},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    res = client.post(f"/api/v1/tests/{test_id}/submit", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    return test_id, res.json()


# --- Admin gate ------------------------------------------------------------


def test_verify_jwt_returns_app_metadata(fake_client):
    admin = verify_jwt(fake_client, "token-admin")
    assert admin["id"] == USER_ADMIN
    assert admin["app_metadata"] == {"is_admin": True}
    student = verify_jwt(fake_client, "token-user-a")
    assert student["id"] == USER_A
    assert student["app_metadata"] == {}


def test_admin_routes_need_a_token(client):
    for route in ADMIN_ROUTES:
        res = client.get(route)
        assert res.status_code == 401, (route, res.text)


def test_admin_routes_reject_invalid_token(client):
    for route in ADMIN_ROUTES:
        res = client.get(route, headers=auth_headers("token-nope"))
        assert res.status_code == 401, (route, res.text)


def test_non_admin_gets_404_on_every_admin_route(client):
    """Doc 05 §4: 404, never 403 — a 403 would confirm the route exists."""
    for route in ADMIN_ROUTES:
        res = client.get(route, headers=auth_headers("token-user-a"))
        assert res.status_code == 404, (route, res.text)
        assert res.json()["error"]["code"] == "not_found", res.text


def test_is_admin_in_body_is_ignored_and_logged(client, engine_db, caplog):
    """No request body can confer admin: the field is ignored by
    the handler, logged as a validation anomaly, and the user
    stays a non-admin."""
    with caplog.at_level("WARNING"):
        res = client.post(
            "/api/v1/me",
            json={"full_name": "Sneaky Student", "is_admin": True},
            headers=auth_headers("token-user-a"),
        )
    assert res.status_code in (200, 201), res.text
    assert "role field in request body ignored" in caplog.text
    res = client.get("/api/v1/admin/overview", headers=auth_headers("token-user-a"))
    assert res.status_code == 404, res.text


# --- Admin sees real rows ----------------------------------------------------


def test_admin_sees_real_rows(client, seeded_doc):
    doc_id, job_id, question_ids = seeded_doc
    _create_profile(client)
    res = client.get("/api/v1/admin/overview", headers=_admin_headers())
    assert res.status_code == 200, res.text
    overview = res.json()
    assert overview["users"] == 1
    assert overview["documents"] == 1
    assert overview["jobs"] == 1
    assert overview["jobs_by_status"] == {"done": 1}
    assert overview["questions"] == 3
    assert overview["errors"] == 0

    res = client.get("/api/v1/admin/users", headers=_admin_headers())
    assert res.status_code == 200, res.text
    users = res.json()
    assert users["total"] == 1
    assert users["items"][0]["full_name"] == "Test Student"
    assert users["items"][0]["documents"] == 1
    assert users["items"][0]["tests"] == 0
    # The engine stores NO student email — the admin list must not invent one.
    assert "email" not in users["items"][0]

    res = client.get("/api/v1/admin/documents", headers=_admin_headers())
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["title"] == "Model Paper 66"
    assert res.json()["items"][0]["latest_job_status"] == "done"

    res = client.get("/api/v1/admin/jobs", headers=_admin_headers())
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["status"] == "done"
    assert res.json()["items"][0]["error_rows"] == 0

    res = client.get("/api/v1/admin/questions", headers=_admin_headers())
    assert res.json()["total"] == 3
    items = res.json()["items"]
    assert sorted(i["correct_index"] for i in items) == [0, 1, 2]
    assert all(i["options_count"] == 4 for i in items)


def test_admin_questions_filters(client, seeded_doc):
    doc_id, job_id, question_ids = seeded_doc
    res = client.get(
        "/api/v1/admin/questions", params={"search": "capital"}, headers=_admin_headers()
    )
    assert res.status_code == 200, res.text
    assert res.json()["total"] == 1
    assert "capital" in res.json()["items"][0]["text"].lower()
    res = client.get(
        "/api/v1/admin/questions",
        params={"validation_status": "answered"},
        headers=_admin_headers(),
    )
    assert res.json()["total"] == 3
    # The store writes the MCQ status ("answered"), never the model
    # default "unreviewed" — so that filter honestly returns 0 here.
    res = client.get(
        "/api/v1/admin/questions",
        params={"validation_status": "unreviewed"},
        headers=_admin_headers(),
    )
    assert res.json()["total"] == 0
    res = client.get(
        "/api/v1/admin/questions",
        params={"document_id": str(doc_id)},
        headers=_admin_headers(),
    )
    assert res.json()["total"] == 3
    res = client.get(
        "/api/v1/admin/questions",
        params={"document_id": str(uuid.uuid4())},
        headers=_admin_headers(),
    )
    assert res.json()["total"] == 0


def test_admin_jobs_error_surface(client, seeded_doc, engine_db):
    doc_id, job_id, question_ids = seeded_doc
    session = engine_db()
    session.add(
        db.ProcessingError(
            document_id=doc_id,
            job_id=job_id,
            stage="ocr",
            error_code="ocr_failed",
            message="Tesseract timed out on page 1.",
        )
    )
    session.commit()
    session.close()
    res = client.get("/api/v1/admin/jobs", headers=_admin_headers())
    assert res.status_code == 200, res.text
    assert res.json()["items"][0]["error_rows"] == 1
    res = client.get("/api/v1/admin/errors", headers=_admin_headers())
    assert res.status_code == 200, res.text
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["error_code"] == "ocr_failed"
    assert res.json()["items"][0]["document_title"] == "Model Paper 66"
    assert res.json()["items"][0]["stage"] == "ocr"


# --- Notifications -----------------------------------------------------------


def test_notifications_crud_and_ownership(client, engine_db):
    session = engine_db()
    create_notification(
        session,
        uuid.UUID(USER_A),
        type="upload_done",
        title="Processing complete: Model Paper 66",
        body="3 questions, 3 with answers.",
        link="/dashboard/documents/x",
    )
    create_notification(
        session,
        uuid.UUID(USER_A),
        type="result_ready",
        title="Result ready: M9 Test",
        body="2 out of 3.",
        link="/dashboard/tests/x/result",
    )
    session.commit()
    session.close()

    res = client.get("/api/v1/notifications", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 2
    assert body["unread_count"] == 2
    # Both rows are created in the same second (SQLite timestamp
    # precision) so their relative order is not asserted — only
    # that both types are present.
    assert {item["type"] for item in body["items"]} == {"upload_done", "result_ready"}
    first_id = body["items"][0]["id"]

    res = client.get(
        "/api/v1/notifications",
        params={"unread_only": True},
        headers=auth_headers("token-user-a"),
    )
    assert res.json()["total"] == 2

    res = client.patch(
        f"/api/v1/notifications/{first_id}/read", headers=auth_headers("token-user-a")
    )
    assert res.status_code == 200, res.text
    assert res.json()["is_read"] is True
    # Idempotent: reading a read row returns the same row.
    res = client.patch(
        f"/api/v1/notifications/{first_id}/read", headers=auth_headers("token-user-a")
    )
    assert res.status_code == 200 and res.json()["is_read"] is True

    res = client.get(
        "/api/v1/notifications",
        params={"unread_only": True},
        headers=auth_headers("token-user-a"),
    )
    assert res.json()["total"] == 1
    assert res.json()["unread_count"] == 1

    # Owner isolation: user B sees nothing and cannot mark A's row read.
    res = client.get("/api/v1/notifications", headers=auth_headers("token-user-b"))
    assert res.json()["total"] == 0
    res = client.patch(
        f"/api/v1/notifications/{first_id}/read", headers=auth_headers("token-user-b")
    )
    assert res.status_code == 404, res.text

    # Unauthenticated.
    res = client.get("/api/v1/notifications")
    assert res.status_code == 401
    res = client.patch(f"/api/v1/notifications/{first_id}/read")
    assert res.status_code == 401


def test_submit_writes_test_submitted_and_result_ready(client, seeded_doc):
    doc_id, job_id, question_ids = seeded_doc
    test_id, result = _submit_test(client, question_ids)
    assert result["correct"] == 2
    assert result["incorrect"] == 1
    res = client.get("/api/v1/notifications", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 2
    assert body["unread_count"] == 2
    types = {item["type"] for item in body["items"]}
    assert types == {"test_submitted", "result_ready"}
    by_type = {item["type"]: item for item in body["items"]}
    assert by_type["test_submitted"]["link"] == f"/dashboard/tests/{test_id}"
    assert by_type["result_ready"]["link"] == f"/dashboard/tests/{test_id}/result"
    assert "M9 Test" in by_type["result_ready"]["title"]
    # Hand-checked: 2 correct (+2.0), 1 incorrect (-0.25) = 1.75 / 3.0 = 58.33%.
    assert by_type["result_ready"]["body"] == (
        "Your result for M9 Test is ready — 1.75 out of 3.0 (58.33%)."
    )


# --- Cross-user + transport security -----------------------------------------


def test_cross_user_access_is_404_everywhere(client, seeded_doc):
    doc_id, job_id, question_ids = seeded_doc
    test_id, _result = _submit_test(client, question_ids)
    # B cannot read A's document, test, or result — 404, never a leak.
    res = client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers("token-user-b"))
    assert res.status_code == 404, res.text
    res = client.get(f"/api/v1/tests/{test_id}", headers=auth_headers("token-user-b"))
    assert res.status_code == 404, res.text
    res = client.get(f"/api/v1/tests/{test_id}/result", headers=auth_headers("token-user-b"))
    assert res.status_code == 404, res.text
    # B's own collections list is empty (owner-scoped), and B cannot
    # touch A's collection row.
    res = client.get("/api/v1/collections", headers=auth_headers("token-user-b"))
    assert res.status_code == 200 and res.json()["total"] == 0
    res = client.get("/api/v1/collections", headers=auth_headers("token-user-a"))
    assert res.json()["total"] == 1  # the submit wrote one mistake row (Q3)
    mistake_id = res.json()["collections"][0]["id"]
    res = client.delete(f"/api/v1/collections/{mistake_id}", headers=auth_headers("token-user-b"))
    assert res.status_code == 404, res.text


def test_cors_disallowed_origin_gets_no_headers(client):
    """CORS final (M3): the allow-list is exact, never '*'. A
    disallowed origin gets NO access-control headers back."""
    res = client.get("/health", headers={"Origin": "https://evil.example.com"})
    assert res.status_code == 200, res.text
    assert "access-control-allow-origin" not in res.headers
    res = client.options(
        "/health",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.status_code == 400, res.text
    assert "access-control-allow-origin" not in res.headers
    # An allowed origin DOES get its headers back.
    res = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_security_headers_on_api_responses(client):
    res = client.get("/health")
    assert res.status_code == 200, res.text
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert res.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert res.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert res.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    # Swagger UI keeps working: CSP is skipped for /docs, the other headers stay.
    res = client.get("/docs")
    assert res.status_code == 200, res.text
    assert "content-security-policy" not in res.headers
    assert res.headers["x-frame-options"] == "DENY"


# --- Alembic 0009 --------------------------------------------------------------


def test_migration_0009_notifications_table_on_fresh_db(tmp_path, monkeypatch):
    """A database built ONLY by ``alembic upgrade head`` has the
    M9 notifications table, and a downgrade to 0008 drops it."""
    from alembic.config import Config

    from alembic import command

    db_file = tmp_path / "alembic-m9.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_file}")
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{db_file}")
    from sqlalchemy import inspect

    assert "notifications" in inspect(engine).get_table_names()
    cols = {c["name"] for c in inspect(engine).get_columns("notifications")}
    assert {"id", "user_id", "type", "title", "body", "link", "is_read", "created_at"} <= cols
    command.downgrade(cfg, "0008_m8_collections")
    assert "notifications" not in inspect(engine).get_table_names()
    engine.dispose()
    command.upgrade(cfg, "head")


def test_migration_0009_downgrade_refuses_with_notification_rows(tmp_path, monkeypatch):
    """Doc 03 §6: a downgrade never deletes user data silently."""
    from alembic.config import Config
    from sqlalchemy.orm import sessionmaker

    from alembic import command

    db_file = tmp_path / "alembic-m9-refuse.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_file}")
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{db_file}")
    session = sessionmaker(bind=engine)()
    session.add(
        db.Notification(
            user_id=uuid.UUID(USER_A),
            type="upload_done",
            title="t",
            body="b",
        )
    )
    session.commit()
    session.close()
    with pytest.raises(RuntimeError, match="Refusing downgrade"):
        command.downgrade(cfg, "0008_m8_collections")
    engine.dispose()


def test_exam_session_withholds_answer_key(client, engine_db):
    """M9 SECURITY FIX: the exam session is served to the
    student's browser WHILE the test is in progress — it must
    never carry ``correct_index`` (or ``answer_source``), or the
    key is readable from the network tab. The UI only needs
    ``is_unknown``. The creator's test-detail preview still
    returns the key (post-creation review, own bank) — assert
    that split explicitly so a future refactor does not merge
    the two shapes back together."""
    factory = engine_db
    session = factory()
    doc_id = uuid.uuid4()
    job_id = uuid.uuid4()
    session.add(
        db.Document(
            id=doc_id,
            user_id=uuid.UUID(USER_A),
            title="Session Leak Doc",
            storage_path="inline-parse",
            file_type="pdf",
            file_size_bytes=10,
            page_count=1,
            content_hash="e" * 64,
        )
    )
    session.add(db.Job(id=job_id, user_id=uuid.UUID(USER_A), document_id=doc_id, status="done"))
    session.commit()
    persist_matched_document(
        session,
        document_id=doc_id,
        job_id=job_id,
        matched=MatchedDocument(
            questions=[
                ResolvedMCQ(
                    number=1,
                    text="Scored question?",
                    options=["A", "B", "C", "D"],
                    correct_index=2,
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
                    text="Unknown question?",
                    options=["A", "B", "C", "D"],
                    correct_index=-1,
                    status="unknown",
                    page=1,
                    paper="Paper 66",
                ),
            ],
            qa_pairs=[],
            pending=[],
            counts={"questions": 2, "answered": 1, "unknown": 1, "pending": 0},
        ),
    )
    session.close()

    res = client.post(
        "/api/v1/tests",
        json={
            "name": "M9 Leak Test",
            "question_count": 2,
            "source_type": "all",
            "include_unknown": True,
        },
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 201, res.text
    test_id = res.json()["test_id"]

    # The creator's own preview DOES show the key.
    res = client.get(f"/api/v1/tests/{test_id}", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    detail_snaps = res.json()["snapshots"]
    assert len(detail_snaps) == 2
    assert sorted(s["correct_index"] for s in detail_snaps) == [-1, 2]

    res = client.post(f"/api/v1/tests/{test_id}/start", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    res = client.get(f"/api/v1/tests/{test_id}/session", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    snaps = res.json()["snapshots"]
    assert len(snaps) == 2
    for snap in snaps:
        assert "correct_index" not in snap, snap
        assert "answer_source" not in snap, snap
        assert isinstance(snap["is_unknown"], bool)
    by_text = {s["question_text"]: s for s in snaps}
    assert by_text["Scored question?"]["is_unknown"] is False
    assert by_text["Unknown question?"]["is_unknown"] is True
    # The unknown snapshot still carries its options (rendered
    # disabled by the take page) but no key to leak.
    assert len(by_text["Unknown question?"]["options"]) == 4


def test_admin_questions_count_live_bank_only(client, engine_db):
    """M9 E2E cross-check, found by measuring: the admin overview
    and questions list counted ALL question rows, including a
    soft-deleted document's — while the student bank list
    excludes them (91 vs 131 after a delete + re-upload). The
    admin questions count is the LIVE bank; the deleted document
    itself stays visible in the admin documents list (audit)."""
    from datetime import UTC, datetime

    factory = engine_db
    session = factory()
    doc_id = uuid.uuid4()
    job_id = uuid.uuid4()
    session.add(
        db.Document(
            id=doc_id,
            user_id=uuid.UUID(USER_A),
            title="Delete Me Doc",
            storage_path="inline-parse",
            file_type="pdf",
            file_size_bytes=10,
            page_count=1,
            content_hash="f" * 64,
        )
    )
    session.add(db.Job(id=job_id, user_id=uuid.UUID(USER_A), document_id=doc_id, status="done"))
    session.commit()
    persist_matched_document(
        session,
        document_id=doc_id,
        job_id=job_id,
        matched=MatchedDocument(
            questions=[
                ResolvedMCQ(
                    number=1,
                    text="Live bank question?",
                    options=["A", "B", "C", "D"],
                    correct_index=0,
                    answer_source="trailing-key",
                    confidence=1.0,
                    raw_confidence=1.0,
                    verified=True,
                    status="answered",
                    page=1,
                    paper="Paper 66",
                )
            ],
            qa_pairs=[],
            pending=[],
            counts={"questions": 1, "answered": 1, "unknown": 0, "pending": 0},
        ),
    )
    session.close()

    res = client.get("/api/v1/admin/overview", headers=_admin_headers())
    assert res.status_code == 200, res.text
    assert res.json()["questions"] == 1
    res = client.get("/api/v1/admin/questions", headers=_admin_headers())
    assert res.json()["total"] == 1

    # Soft-delete the document: its question leaves the live bank.
    session = factory()
    doc = session.get(db.Document, doc_id)
    doc.deleted_at = datetime.now(UTC)
    session.commit()
    session.close()

    res = client.get("/api/v1/admin/overview", headers=_admin_headers())
    assert res.json()["questions"] == 0
    res = client.get("/api/v1/admin/questions", headers=_admin_headers())
    assert res.json()["total"] == 0
    # …but the document itself stays in the admin audit list.
    res = client.get("/api/v1/admin/documents", headers=_admin_headers())
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["deleted_at"] is not None
