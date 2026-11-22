# OfficerPath AI — Phase 2, M3 (ADR-011)
# Dual job-store resolution proofs: one store, one vocabulary,
# one job id visible from both read endpoints; the worker claims
# upload-source jobs and skips register-source jobs (bucket bytes).

import uuid

from app.db import models as db
from app.tests.conftest import USER_A, auth_headers, register_payload
from app.workers.processor import claim_next_job


def _register(client, user_id, token, **overrides):
    res = client.post(
        "/api/v1/documents/register",
        json=register_payload(user_id, **overrides),
        headers=auth_headers(token),
    )
    assert res.status_code == 201, res.text
    return res.json()["job"]["id"]


def _job_row(engine_db, job_id):
    session = engine_db()
    try:
        job = session.get(db.Job, uuid.UUID(job_id))
        assert job is not None
        return {"status": job.status, "result_summary": dict(job.result_summary or {})}
    finally:
        session.close()


def test_register_job_visible_from_both_read_endpoints(client, engine_db):
    """ADR-011 proof: a job created by the register path is the SAME
    row the async-jobs path reads (one store, one id, one status)."""
    job_id = _register(client, USER_A, "token-user-a")
    via_jobs = client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers("token-user-a"))
    assert via_jobs.status_code == 200
    via_async = client.get(f"/api/v1/async-jobs/{job_id}", headers=auth_headers("token-user-a"))
    assert via_async.status_code == 200
    assert via_jobs.json()["id"] == via_async.json()["job_id"] == job_id
    assert via_jobs.json()["status"] == via_async.json()["status"] == "queued"


def test_async_job_visible_from_jobs_endpoint(client, engine_db):
    """The reverse direction: an async-jobs submit is visible from
    GET /api/v1/jobs/{id} too."""
    res = client.post(
        "/api/v1/async-jobs/parse",
        files={"file": ("a.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 202, res.text
    job_id = res.json()["job_id"]
    via_jobs = client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers("token-user-a"))
    assert via_jobs.status_code == 200
    assert via_jobs.json()["id"] == job_id
    assert via_jobs.json()["status"] == "queued"


def test_terminal_status_is_done_not_completed(client, engine_db):
    """ADR-011 vocabulary: the terminal status is `done` (the live
    015 check constraint rejects `completed`). A job set to `done`
    reads back as `done` from both endpoints."""
    job_id = _register(client, USER_A, "token-user-a")
    session = engine_db()
    try:
        job = session.get(db.Job, uuid.UUID(job_id))
        job.status = "done"
        session.commit()
    finally:
        session.close()
    for path in (f"/api/v1/jobs/{job_id}", f"/api/v1/async-jobs/{job_id}"):
        res = client.get(path, headers=auth_headers("token-user-a"))
        assert res.status_code == 200
        body = res.json()
        assert body.get("status") == "done"


def test_worker_claims_upload_job_but_skips_register_job(client, engine_db):
    """ADR-011 claim filter: register-source jobs (bucket bytes)
    are never claimed; upload-source jobs (local bytes) are."""
    register_id = _register(client, USER_A, "token-user-a")
    res = client.post(
        "/api/v1/async-jobs/parse",
        files={"file": ("a.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 202, res.text
    async_id = res.json()["job_id"]

    # The register job is skipped even though it is older.
    session = engine_db()
    try:
        claimed = claim_next_job(session)
    finally:
        session.close()
    assert claimed is not None
    assert str(claimed.id) == async_id
    assert claimed.status == "processing"

    # The register job is still queued, untouched.
    assert _job_row(engine_db, register_id)["status"] == "queued"
    assert _job_row(engine_db, register_id)["result_summary"] == {"source": "register"}
    assert _job_row(engine_db, async_id)["result_summary"] in (None, {})


def test_register_job_source_marker_is_register(client, engine_db):
    job_id = _register(client, USER_A, "token-user-a")
    assert _job_row(engine_db, job_id)["result_summary"] == {"source": "register"}


def test_upload_job_source_marker_is_upload(client, engine_db):
    from app.tests.test_ingestion import _pdf

    res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("paper.pdf", _pdf(), "application/pdf")},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    job_id = res.json()["job"]["id"]
    assert _job_row(engine_db, job_id)["result_summary"] == {"source": "upload"}
