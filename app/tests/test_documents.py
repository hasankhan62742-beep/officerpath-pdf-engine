# OfficerPath AI — Phase 2, M4
# Document listing / detail / dashboard summary / soft delete
# (GAP-2) + the end-to-end upload proof: a real CA40 fixture
# uploaded through the real endpoint, processed by the real
# worker, then visible in the real dashboard numbers.
#
# Auth uses the conftest fake Supabase (token-user-a -> USER_A,
# token-user-b -> USER_B). The database is a throwaway SQLite
# file per test; the worker runs in-process via run_once.

import uuid
from pathlib import Path

from app.tests.conftest import auth_headers
from app.tests.test_ingestion import _pdf
from app.workers.runner import run_once

FIX = Path(__file__).resolve().parent / "fixtures/golden/ppsc66"
CA40 = FIX / "ppsc-current-affairs-40-mcqs.pdf"
# The acceptance table photo (same md5 as the Flutter-app
# fixtures copy). Read-only here — the test never writes to it.
TABLE_PHOTO = FIX / "table-computer-q67-81-resent-20261121.jpg"


def _upload(client, data, filename="paper.pdf", token="token-user-a"):
    res = client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, data, "application/pdf")},
        headers=auth_headers(token),
    )
    assert res.status_code == 200, res.text
    return res.json()


def _summary(client, token="token-user-a"):
    res = client.get("/api/v1/dashboard/summary", headers=auth_headers(token))
    assert res.status_code == 200, res.text
    return res.json()


def test_dashboard_empty_for_fresh_user(client, engine_db):
    """A fresh user sees honest zeros and an empty list — never
    invented totals."""
    body = _summary(client)
    assert body["documents_total"] == 0
    assert body["jobs_by_status"] == {
        "queued": 0,
        "uploading": 0,
        "processing": 0,
        "done": 0,
        "failed": 0,
        "cancelled": 0,
    }
    assert body["recent_documents"] == []
    res = client.get("/api/v1/documents", headers=auth_headers("token-user-a"))
    assert res.status_code == 200
    assert res.json() == {"documents": [], "total": 0, "limit": 20, "offset": 0}


def test_upload_then_list_and_summary(client, engine_db):
    """Upload -> list shows the document with its queued job ->
    summary counts it."""
    uploaded = _upload(client, CA40.read_bytes(), "ca40.pdf")
    job_id = uploaded["job"]["id"]
    document_id = uploaded["document"]["id"]
    assert uploaded["job"]["status"] == "queued"

    res = client.get("/api/v1/documents", headers=auth_headers("token-user-a"))
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    item = body["documents"][0]
    assert item["id"] == document_id
    assert item["title"] == "ca40.pdf"
    assert item["file_type"] == "pdf"
    assert item["job"]["id"] == job_id
    assert item["job"]["status"] == "queued"
    assert item["questions"] is None  # no parse yet

    summary = _summary(client)
    assert summary["documents_total"] == 1
    assert summary["jobs_by_status"]["queued"] == 1
    assert summary["jobs_by_status"]["done"] == 0
    assert len(summary["recent_documents"]) == 1
    assert summary["recent_documents"][0]["id"] == document_id


def test_end_to_end_upload_worker_dashboard(client, engine_db):
    """M4 E2E proof (API level — the exact endpoints the frontend
    calls): upload CA40 -> worker completes it -> dashboard and
    list show the real parse counts (40 questions)."""
    uploaded = _upload(client, CA40.read_bytes(), "ca40.pdf")
    document_id = uploaded["document"]["id"]

    summary = run_once(engine_db)
    assert summary is not None
    assert summary["status"] == "done", summary
    assert summary["questions"] == 40

    res = client.get(f"/api/v1/documents/{document_id}", headers=auth_headers("token-user-a"))
    assert res.status_code == 200
    detail = res.json()
    assert detail["document"]["id"] == document_id
    assert detail["job"]["status"] == "done"
    assert detail["job"]["result_summary"]["questions"] == 40
    assert detail["job"]["result_summary"]["answered"] >= 30
    stage_names = {s["stage"] for s in detail["stages"]}
    assert "completed" in stage_names

    summary = _summary(client)
    assert summary["documents_total"] == 1
    assert summary["jobs_by_status"]["done"] == 1
    assert summary["jobs_by_status"]["queued"] == 0
    recent = summary["recent_documents"][0]
    assert recent["questions"] == 40
    assert recent["answered"] >= 30

    res = client.get("/api/v1/documents?status=done", headers=auth_headers("token-user-a"))
    assert res.json()["total"] == 1
    res = client.get("/api/v1/documents?status=queued", headers=auth_headers("token-user-a"))
    assert res.json()["total"] == 0


def test_table_photo_upload_completes_through_worker(client, engine_db):
    """The second acceptance file: a real table photo uploaded and
    processed by the worker (M8 sync-parse result was 0 questions /
    2 pending — the async path must agree)."""
    data = TABLE_PHOTO.read_bytes()
    res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("table.jpg", data, "image/jpeg")},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    summary = run_once(engine_db)
    assert summary is not None
    assert summary["status"] == "done", summary
    assert summary["questions"] == 0
    detail = client.get(
        f"/api/v1/documents/{res.json()['document']['id']}",
        headers=auth_headers("token-user-a"),
    ).json()
    assert detail["job"]["result_summary"]["questions"] == 0
    assert detail["job"]["result_summary"]["pending"] == 2


def test_list_pagination_and_status_filter(client, engine_db):
    _upload(client, CA40.read_bytes(), "one.pdf")
    _upload(client, _pdf(), "two.pdf")
    res = client.get("/api/v1/documents?limit=1&offset=0", headers=auth_headers("token-user-a"))
    assert res.status_code == 200
    page1 = res.json()
    assert page1["total"] == 2
    assert len(page1["documents"]) == 1
    res = client.get("/api/v1/documents?limit=1&offset=1", headers=auth_headers("token-user-a"))
    page2 = res.json()
    assert len(page2["documents"]) == 1
    assert page2["documents"][0]["id"] != page1["documents"][0]["id"]
    # Newest first.
    assert page1["documents"][0]["title"] == "two.pdf"
    # Bad status is a 422, never a 500.
    res = client.get("/api/v1/documents?status=bogus", headers=auth_headers("token-user-a"))
    assert res.status_code == 422


def test_detail_and_list_are_per_user(client, engine_db):
    uploaded = _upload(client, CA40.read_bytes(), "ca40.pdf")
    document_id = uploaded["document"]["id"]
    # USER_B sees nothing: empty list, 404 on the detail.
    res = client.get("/api/v1/documents", headers=auth_headers("token-user-b"))
    assert res.json()["total"] == 0
    res = client.get(f"/api/v1/documents/{document_id}", headers=auth_headers("token-user-b"))
    assert res.status_code == 404
    res = client.get("/api/v1/dashboard/summary", headers=auth_headers("token-user-b"))
    assert res.json()["documents_total"] == 0
    # Unknown and malformed ids are 404, never 500.
    res = client.get(f"/api/v1/documents/{uuid.uuid4()}", headers=auth_headers("token-user-a"))
    assert res.status_code == 404
    res = client.get("/api/v1/documents/not-a-uuid", headers=auth_headers("token-user-a"))
    assert res.status_code == 404
    # No token at all is 401.
    assert client.get("/api/v1/documents").status_code == 401
    assert client.get("/api/v1/dashboard/summary").status_code == 401
    assert client.get(f"/api/v1/documents/{document_id}").status_code == 401


def test_delete_soft_deletes_and_cancels_queued_job(client, engine_db):
    uploaded = _upload(client, CA40.read_bytes(), "ca40.pdf")
    document_id = uploaded["document"]["id"]
    job_id = uploaded["job"]["id"]
    res = client.delete(f"/api/v1/documents/{document_id}", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    assert res.json() == {"document_id": document_id, "deleted": True, "job_cancelled": True}
    # The queued job is cancelled, not left running.
    res = client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers("token-user-a"))
    assert res.json()["status"] == "cancelled"
    # The document is gone from list/summary/detail.
    assert (
        client.get("/api/v1/documents", headers=auth_headers("token-user-a")).json()["total"] == 0
    )
    assert _summary(client)["documents_total"] == 0
    assert (
        client.get(
            f"/api/v1/documents/{document_id}", headers=auth_headers("token-user-a")
        ).status_code
        == 404
    )
    # Deleting again is 404; another user cannot delete it either.
    assert (
        client.delete(
            f"/api/v1/documents/{document_id}", headers=auth_headers("token-user-a")
        ).status_code
        == 404
    )
    # Re-uploading the same file after delete creates a FRESH
    # document (soft-deleted rows do not dedup).
    again = _upload(client, CA40.read_bytes(), "ca40.pdf")
    assert again["document"]["id"] != document_id
    assert again["idempotent_replay"] is False


def test_delete_done_document_leaves_job_terminal(client, engine_db):
    uploaded = _upload(client, CA40.read_bytes(), "ca40.pdf")
    document_id = uploaded["document"]["id"]
    summary = run_once(engine_db)
    assert summary is not None and summary["status"] == "done"
    res = client.delete(f"/api/v1/documents/{document_id}", headers=auth_headers("token-user-a"))
    assert res.status_code == 200
    assert res.json()["job_cancelled"] is False
    assert _summary(client)["documents_total"] == 0


def test_delete_other_users_document_is_404(client, engine_db):
    uploaded = _upload(client, CA40.read_bytes(), "ca40.pdf")
    document_id = uploaded["document"]["id"]
    res = client.delete(f"/api/v1/documents/{document_id}", headers=auth_headers("token-user-b"))
    assert res.status_code == 404
    # Still there for the owner.
    assert (
        client.get("/api/v1/documents", headers=auth_headers("token-user-a")).json()["total"] == 1
    )
