# OfficerPath AI — PDF Engine (Phase 1, M6)
# Review API tests: parse, review list, corrections, report.
# Auth uses the conftest fake Supabase (token-user-a -> USER_A).

import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.v1.review as review_api
from app.db import models as db
from app.db.models import Base
from app.tests.conftest import USER_A, auth_headers

FIX = Path(__file__).resolve().parent / "fixtures/golden/ppsc66"
CA40 = FIX / "ppsc-current-affairs-40-mcqs.pdf"


@pytest.fixture
def db_session_factory(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/review.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(review_api, "get_session", lambda: factory())
    yield factory
    engine.dispose()


def _parse(client, db_session_factory):
    with CA40.open("rb") as fh:
        resp = client.post(
            "/api/v1/documents/parse",
            files={"file": ("ca40.pdf", fh, "application/pdf")},
            headers=auth_headers("token-user-a"),
        )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_parse_digital_pdf_persists_and_reports(client, db_session_factory) -> None:
    body = _parse(client, db_session_factory)
    assert body["persisted"] is True
    assert body["is_digital"] is True
    assert body["page_count"] == 6
    assert body["document_id"]
    assert body["job_id"]
    matched = body["matched"]
    # CA40: 40 MCQs, bold answers.
    assert matched["counts"]["questions"] == 40
    assert matched["answered"] >= 30
    report = body["report"]
    assert report["counts"]["questions"] == 40
    assert "by_answer_source" in report
    # Stored rows exist.
    session = db_session_factory()
    rows = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.document_id == uuid.UUID(body["document_id"]))
        .all()
    )
    assert len(rows) == 40
    session.close()


def test_parse_without_database_still_returns_result(client, monkeypatch) -> None:
    monkeypatch.setattr(review_api, "get_session", lambda: None)
    with CA40.open("rb") as fh:
        resp = client.post(
            "/api/v1/documents/parse",
            files={"file": ("ca40.pdf", fh, "application/pdf")},
            headers=auth_headers("token-user-a"),
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["persisted"] is False
    assert body["job_id"] is None
    assert body["matched"]["counts"]["questions"] == 40


def test_parse_rejects_unsupported_type(client) -> None:
    # A2: TXT/DOCX are accepted now, so the rejection case is a
    # genuinely unsupported type — same 422 contract as before.
    resp = client.post(
        "/api/v1/documents/parse",
        files={"file": ("x.xyz", b"hello", "application/octet-stream")},
        headers=auth_headers("token-user-a"),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_file"


def test_parse_requires_auth(client) -> None:
    with CA40.open("rb") as fh:
        resp = client.post(
            "/api/v1/documents/parse",
            files={"file": ("ca40.pdf", fh, "application/pdf")},
        )
    assert resp.status_code == 401


def test_review_list_and_report(client, db_session_factory) -> None:
    body = _parse(client, db_session_factory)
    resp = client.get(
        f"/api/v1/jobs/{body['job_id']}/review",
        headers=auth_headers("token-user-a"),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == body["job_id"]
    assert data["count"] == len(data["items"])
    for item in data["items"]:
        assert item["status"] in ("pending", "unknown")
        assert isinstance(item["options"], list)
    resp = client.get(
        f"/api/v1/documents/{body['document_id']}/report",
        headers=auth_headers("token-user-a"),
    )
    assert resp.status_code == 200
    assert resp.json()["questions_extracted"] == 40


def test_review_list_other_user_gets_404(client, db_session_factory) -> None:
    body = _parse(client, db_session_factory)
    resp = client.get(
        f"/api/v1/jobs/{body['job_id']}/review",
        headers=auth_headers("token-user-b"),
    )
    assert resp.status_code == 404


def test_correction_flow(client, db_session_factory) -> None:
    body = _parse(client, db_session_factory)
    session = db_session_factory()
    row = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.document_id == uuid.UUID(body["document_id"]))
        .order_by(db.ExtractedQuestion.question_number)
        .first()
    )
    question_id = row.id
    original_text = row.original_text
    session.close()
    resp = client.post(
        f"/api/v1/documents/{body['document_id']}/questions/{question_id}/corrections",
        json={"field": "answer", "new_value": "A", "reason": "reviewer check"},
        headers=auth_headers("token-user-a"),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["new_value"] == "A"
    assert data["validation_status"] == "answered"
    assert data["validation_issues"] == []
    # Original extraction untouched; audit rows recorded.
    session = db_session_factory()
    row = session.query(db.ExtractedQuestion).filter(db.ExtractedQuestion.id == question_id).one()
    assert row.original_text == original_text
    corrections = (
        session.query(db.ManualCorrection)
        .filter(db.ManualCorrection.document_id == uuid.UUID(body["document_id"]))
        .all()
    )
    assert len(corrections) == 1
    assert str(corrections[0].user_id) == USER_A
    session.close()


def test_correction_rejects_bad_field(client, db_session_factory) -> None:
    body = _parse(client, db_session_factory)
    session = db_session_factory()
    row = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.document_id == uuid.UUID(body["document_id"]))
        .first()
    )
    question_id = row.id
    session.close()
    resp = client.post(
        f"/api/v1/documents/{body['document_id']}/questions/{question_id}/corrections",
        json={"field": "paper", "new_value": "Paper 67"},
        headers=auth_headers("token-user-a"),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_correction"


def test_correction_other_user_gets_404(client, db_session_factory) -> None:
    body = _parse(client, db_session_factory)
    session = db_session_factory()
    row = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.document_id == uuid.UUID(body["document_id"]))
        .first()
    )
    question_id = row.id
    session.close()
    resp = client.post(
        f"/api/v1/documents/{body['document_id']}/questions/{question_id}/corrections",
        json={"field": "answer", "new_value": "A"},
        headers=auth_headers("token-user-b"),
    )
    assert resp.status_code == 404


def test_review_endpoints_503_without_database(client, monkeypatch) -> None:
    monkeypatch.setattr(review_api, "get_session", lambda: None)
    resp = client.get(
        "/api/v1/jobs/11111111-1111-1111-1111-111111111111/review",
        headers=auth_headers("token-user-a"),
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "database_unavailable"
