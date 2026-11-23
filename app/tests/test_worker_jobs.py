# OfficerPath AI — Phase 1, M7
# Background jobs: async submit -> worker processes -> done /
# failed / cancelled, with stage history, retry, and per-user
# isolation. Auth uses the conftest fake Supabase (token-user-a
# -> USER_A). The database is a throwaway SQLite file per test;
# the worker runs in-process via run_once (no threads).

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.v1.async_jobs as async_jobs_api
import app.api.v1.review as review_api
from app.config import settings
from app.db import models as db
from app.db.models import Base
from app.tests.conftest import USER_A, auth_headers
from app.workers.processor import claim_next_job, process_job
from app.workers.runner import run_once

FIX = __import__("pathlib").Path(__file__).resolve().parent / "fixtures/golden/ppsc66"
CA40 = FIX / "ppsc-current-affairs-40-mcqs.pdf"


@pytest.fixture
def db_factory(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/jobs.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(async_jobs_api, "get_session", lambda: factory())
    monkeypatch.setattr(review_api, "get_session", lambda: factory())
    monkeypatch.setattr(settings, "storage_root", str(tmp_path / "storage"))
    yield factory
    engine.dispose()


def _submit(client, data: bytes, filename: str = "ca40.pdf"):
    resp = client.post(
        "/api/v1/async-jobs/parse",
        files={"file": (filename, data, "application/pdf")},
        headers=auth_headers("token-user-a"),
    )
    assert resp.status_code == 202, resp.text
    return resp.json()


def test_async_parse_queued_then_worker_completes(client, db_factory) -> None:
    body = _submit(client, CA40.read_bytes())
    assert body["status"] == "queued"
    job_id = body["job_id"]
    # Poll before the worker runs: still queued.
    res = client.get(f"/api/v1/async-jobs/{job_id}", headers=auth_headers("token-user-a"))
    assert res.status_code == 200
    assert res.json()["status"] == "queued"
    # The worker claims and processes it in-process.
    summary = run_once(db_factory)
    assert summary is not None
    # ADR-011: terminal job status is "done" now.
    assert summary["status"] == "done"
    assert summary["questions"] == 40
    assert summary["answered"] >= 30
    # Stage history: the real phases ran, with timings.
    res = client.get(f"/api/v1/async-jobs/{job_id}", headers=auth_headers("token-user-a"))
    status = res.json()
    assert status["status"] == "done"
    stage_names = {s["stage"] for s in status["stages"]}
    for expected in (
        "queued",
        "validated",
        "extracted",
        "answers_detected",
        "matched",
        "scored",
        "completed",
    ):
        assert expected in stage_names, stage_names
    assert status["result_summary"]["questions"] == 40
    # Queue is empty now.
    assert run_once(db_factory) is None


def test_worker_failure_then_retry_recovers(client, db_factory) -> None:
    # Corrupt PDF bytes (valid magic, unreadable content): the
    # worker fails the job with the reason recorded, never crashes.
    body = _submit(client, b"%PDF-1.4\n%garbage-not-a-pdf", "bad.pdf")
    job_id = body["job_id"]
    summary = run_once(db_factory)
    assert summary["status"] == "failed"
    assert summary["error"]
    res = client.get(f"/api/v1/async-jobs/{job_id}", headers=auth_headers("token-user-a"))
    assert res.json()["status"] == "failed"
    assert res.json()["error"]
    # Retry re-queues it; replacing the stored bytes with a good
    # PDF lets the same job complete (the retry path works).
    res = client.post(f"/api/v1/async-jobs/{job_id}/retry", headers=auth_headers("token-user-a"))
    assert res.status_code == 200
    assert res.json()["status"] == "queued"
    assert res.json()["retry_count"] == 1
    from app.storage.local import LocalDiskStorage

    session = db_factory()
    job = session.get(db.Job, uuid.UUID(job_id))
    document = session.get(db.Document, job.document_id)
    LocalDiskStorage(settings.storage_root).delete(document.storage_path)
    LocalDiskStorage(settings.storage_root).put(document.storage_path, CA40.read_bytes())
    session.close()
    summary = run_once(db_factory)
    # ADR-011: terminal job status is "done" now.
    assert summary["status"] == "done"
    assert summary["questions"] == 40


def test_cancel_queued_job(client, db_factory) -> None:
    body = _submit(client, CA40.read_bytes())
    job_id = body["job_id"]
    res = client.post(f"/api/v1/async-jobs/{job_id}/cancel", headers=auth_headers("token-user-a"))
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"
    # Nothing to claim: the worker leaves it alone.
    assert run_once(db_factory) is None
    # A cancelled job cannot be cancelled again.
    res = client.post(f"/api/v1/async-jobs/{job_id}/cancel", headers=auth_headers("token-user-a"))
    assert res.status_code == 409


def test_cancel_processing_job_is_cancelled_not_failed(client, db_factory) -> None:
    # Claim the job, flag cancel, then process: the worker must
    # record cancelled (not failed) at the first stage boundary.
    body = _submit(client, CA40.read_bytes())
    job_id = body["job_id"]
    session = db_factory()
    job = claim_next_job(session)
    assert job is not None and str(job.id) == job_id
    job.result_summary = {"cancel_requested": True}
    session.commit()
    session.close()
    session = db_factory()
    job = session.get(db.Job, uuid.UUID(job_id))
    from app.storage.local import LocalDiskStorage

    summary = process_job(
        session, job, storage=LocalDiskStorage(settings.storage_root), settings=settings
    )
    assert summary["status"] == "cancelled"
    session.close()
    session = db_factory()
    job = session.get(db.Job, uuid.UUID(job_id))
    assert job.status == "cancelled"
    session.close()


def test_stage_timeout_fails_job_with_stage_named(client, db_factory, monkeypatch) -> None:
    # Deterministic timeout proof: a fake parse that spends 0.3 s
    # in the OCR stage with a 0.1 s per-stage timeout must fail the
    # job naming the OCR stage (never left hanging, never a bare
    # crash). The timeout is cumulative per stage.
    import time as _time

    import app.workers.processor as processor

    def _slow_parse(data, doc_id, *, settings, on_stage):
        on_stage("classify", {"is_digital": False, "page_count": 1})
        _time.sleep(0.3)
        on_stage("ocr", {"page": 1, "psm": 3})
        raise AssertionError("must not reach here — the timeout fires first")

    monkeypatch.setattr(processor, "parse_document_bytes", _slow_parse)
    monkeypatch.setattr(settings, "worker_stage_timeout_seconds", 0.1)
    body = _submit(client, CA40.read_bytes())
    job_id = body["job_id"]
    summary = run_once(db_factory)
    assert summary["status"] == "failed"
    assert "ocr" in summary["error"]
    assert "timeout" in summary["error"]
    assert summary["failed_at_stage"] == "ocr"
    res = client.get(f"/api/v1/async-jobs/{job_id}", headers=auth_headers("token-user-a"))
    assert res.json()["status"] == "failed"
    assert "ocr" in (res.json()["error"] or "")


def test_sync_parse_job_has_no_stored_bytes(client, db_factory) -> None:
    # A sync-parse job (storage_path="inline-parse") queued by hand
    # fails fast with a clear reason — it is never re-processed
    # from bytes that do not exist.
    session = db_factory()
    document = db.Document(
        user_id=uuid.UUID(USER_A),
        title="inline.pdf",
        storage_path="inline-parse",
        file_type="pdf",
        file_size_bytes=10,
    )
    session.add(document)
    session.flush()
    job = db.Job(user_id=uuid.UUID(USER_A), document_id=document.id, status="queued")
    session.add(job)
    session.commit()
    session.close()
    summary = run_once(db_factory)
    assert summary["status"] == "failed"
    assert "no stored bytes" in summary["error"]


def test_claim_is_atomic_second_claim_gets_nothing(client, db_factory) -> None:
    _submit(client, CA40.read_bytes())
    session = db_factory()
    first = claim_next_job(session)
    assert first is not None
    assert claim_next_job(session) is None
    session.close()


def test_async_jobs_are_per_user(client, db_factory) -> None:
    body = _submit(client, CA40.read_bytes())
    job_id = body["job_id"]
    for method in ("get", "post"):
        path = (
            f"/api/v1/async-jobs/{job_id}"
            if method == "get"
            else f"/api/v1/async-jobs/{job_id}/cancel"
        )
        res = getattr(client, method)(path, headers=auth_headers("token-user-b"))
        assert res.status_code == 404, (method, res.text)
    res = client.get(f"/api/v1/async-jobs/{job_id}", headers=auth_headers("token-user-a"))
    assert res.status_code == 200


def test_async_parse_rejects_non_pdf_and_requires_auth(client, db_factory) -> None:
    res = client.post(
        "/api/v1/async-jobs/parse",
        files={"file": ("x.txt", b"hello", "text/plain")},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 422
    res = client.post(
        "/api/v1/async-jobs/parse",
        files={"file": ("ca40.pdf", CA40.read_bytes(), "application/pdf")},
    )
    assert res.status_code == 401


def test_retry_only_failed_or_cancelled(client, db_factory) -> None:
    body = _submit(client, CA40.read_bytes())
    res = client.post(
        f"/api/v1/async-jobs/{body['job_id']}/retry", headers=auth_headers("token-user-a")
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "job_not_retryable"


# M10 — async-jobs dedup (M7 edge, fixed here): re-submitting
# identical bytes to POST /api/v1/async-jobs/parse used to 500 with
# UNIQUE constraint failed on documents.user_id + content_hash.
# The decision (consistent with the register contract): replay
# returns the ORIGINAL job with 200 + idempotent_replay, never a
# new document and never a 500.
def _resubmit(client, data: bytes, token: str = "token-user-a"):
    return client.post(
        "/api/v1/async-jobs/parse",
        files={"file": ("ca40.pdf", data, "application/pdf")},
        headers=auth_headers(token),
    )


def test_async_parse_replay_returns_original_job(client, db_factory) -> None:
    data = CA40.read_bytes()
    first = _submit(client, data)
    assert first["idempotent_replay"] is False
    # Worker completes the first job, so the replay answers with the
    # finished job's status — polling it shows the real result.
    summary = run_once(db_factory)
    assert summary is not None and summary["status"] == "done"
    res = _resubmit(client, data)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["idempotent_replay"] is True
    assert body["job_id"] == first["job_id"]
    assert body["document_id"] == first["document_id"]
    assert body["status"] == "done"
    # Exactly one document + one job, and one stored object: the
    # replay stored no new bytes and created no new rows.
    session = db_factory()
    assert session.query(db.Document).filter(db.Document.user_id == uuid.UUID(USER_A)).count() == 1
    assert session.query(db.Job).filter(db.Job.user_id == uuid.UUID(USER_A)).count() == 1
    session.close()
    stored = [p for p in Path(settings.storage_root).rglob("*") if p.is_file()]
    assert len(stored) == 1, stored


def test_async_parse_replay_after_soft_delete_creates_fresh_job(client, db_factory) -> None:
    data = CA40.read_bytes()
    first = _submit(client, data)
    session = db_factory()
    doc = session.get(db.Document, uuid.UUID(first["document_id"]))
    doc.deleted_at = datetime.now(UTC)
    session.commit()
    session.close()
    # A soft-deleted document never blocks a fresh upload of the
    # same file (M6 partial-index rule): 202, new document + job.
    res = _resubmit(client, data)
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["idempotent_replay"] is False
    assert body["document_id"] != first["document_id"]
    assert body["job_id"] != first["job_id"]


def test_async_parse_same_bytes_different_user_is_fresh(client, db_factory) -> None:
    data = CA40.read_bytes()
    first = _submit(client, data)
    # The dedup key is (user_id, content_hash): another user's
    # identical bytes are their own document, not a replay.
    res = _resubmit(client, data, token="token-user-b")
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["idempotent_replay"] is False
    assert body["document_id"] != first["document_id"]
    assert body["job_id"] != first["job_id"]
