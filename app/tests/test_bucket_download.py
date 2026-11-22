# OfficerPath AI — Phase 2, M4
# Bucket-download proofs: a register-source job's bytes live in
# the Supabase bucket, not on local disk. process_job downloads
# them (via the injectable `bucket_downloader`) into local storage
# before parsing. The live bucket is MISSING (M3: migration 016
# not applied), so the real download cannot be proven against
# live Supabase here — these tests prove the wiring locally with
# a fake downloader, and the failure modes name the storage
# problem instead of failing silently.
#
# The download function itself (download_bucket_bytes) is proven
# against a fake service client in test_storage_download.py.

import uuid
from pathlib import Path

from app.config import settings
from app.core.errors import ApiError
from app.db import models as db
from app.storage.local import LocalDiskStorage
from app.tests.conftest import USER_A, auth_headers, register_payload
from app.workers.runner import run_once

FIX = Path(__file__).resolve().parent / "fixtures/golden/ppsc66"
CA40 = FIX / "ppsc-current-affairs-40-mcqs.pdf"


def _register(client, user_id, token, **overrides):
    res = client.post(
        "/api/v1/documents/register",
        json=register_payload(user_id, **overrides),
        headers=auth_headers(token),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    return body["job"]["id"], body["document"]["storage_path"]


def _job_row(engine_db, job_id):
    session = engine_db()
    try:
        job = session.get(db.Job, uuid.UUID(job_id))
        assert job is not None
        return {"status": job.status, "error": job.error, "result_summary": job.result_summary}
    finally:
        session.close()


def test_register_job_downloads_bytes_then_completes(client, engine_db):
    """The M4 wiring: a register job's bytes come from the bucket
    (fake downloader returns the real CA40 fixture) and the job
    completes with the real parse counts — 40 questions."""
    job_id, storage_path = _register(client, USER_A, "token-user-a")
    calls = []

    def fake_downloader(path):
        calls.append(path)
        assert path == storage_path
        return CA40.read_bytes()

    summary = run_once(engine_db, bucket_downloader=fake_downloader)
    assert summary is not None
    assert summary["status"] == "done", summary
    assert summary["questions"] == 40
    assert calls == [storage_path]
    row = _job_row(engine_db, job_id)
    assert row["status"] == "done"
    assert row["result_summary"]["questions"] == 40
    # The downloaded bytes are now cached in local storage under
    # the same path (write-once cache for later reads).
    assert LocalDiskStorage(settings.storage_root).exists(storage_path)
    assert run_once(engine_db, bucket_downloader=fake_downloader) is None


def test_register_job_fails_with_named_error_when_bucket_missing(client, engine_db):
    """Live bucket missing (migration 016 unapplied) is the real
    failure mode: the job FAILS with a named storage error — it is
    never silently skipped and never stuck in processing."""
    job_id, _path = _register(client, USER_A, "token-user-a")

    def missing_bucket_downloader(path):
        raise ApiError(
            status_code=500,
            code="storage_bucket_missing",
            message="Storage bucket 'pdf-documents' does not exist. "
            "Apply migration 016 (Supabase Dashboard) to create it.",
        )

    summary = run_once(engine_db, bucket_downloader=missing_bucket_downloader)
    assert summary is not None
    assert summary["status"] == "failed", summary
    row = _job_row(engine_db, job_id)
    assert row["status"] == "failed"
    assert row["error"] is not None
    assert "bucket" in row["error"].lower()
    assert "016" in row["error"]


def test_register_job_with_local_bytes_skips_download(client, engine_db):
    """Bytes already on local disk (e.g. a previous download, or a
    re-run) are used as-is — the downloader is never called."""
    job_id, storage_path = _register(client, USER_A, "token-user-a")
    LocalDiskStorage(settings.storage_root).put(storage_path, CA40.read_bytes())

    def must_not_be_called(path):
        raise AssertionError(f"downloader must not be called, got {path!r}")

    summary = run_once(engine_db, bucket_downloader=must_not_be_called)
    assert summary is not None
    assert summary["status"] == "done", summary
    assert summary["questions"] == 40
    assert _job_row(engine_db, job_id)["status"] == "done"
