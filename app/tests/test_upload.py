# OfficerPath AI — PDF Engine (Phase 1, M1) — tests
# Upload API: single + batch, auth, ownership, validation rejections,
# SHA-256 dedup replay. Uses the fake Supabase client + a tmp local
# storage root — no network, no live Supabase.

import pytest

from app.config import settings
from app.tests.conftest import USER_A, auth_headers, register_payload
from app.tests.test_ingestion import _pdf, _png


@pytest.fixture(autouse=True)
def _tmp_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_root", str(tmp_path / "storage"))
    monkeypatch.setattr(settings, "database_url", None)


def _upload(client, token, filename, data, mime="application/pdf"):
    return client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, data, mime)},
        headers=auth_headers(token),
    )


def test_upload_pdf_stored(client, fake_client):
    res = _upload(client, "token-user-a", "paper-66.pdf", _pdf())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "stored"
    assert body["document"]["file_type"] == "pdf"
    assert body["job"]["status"] == "queued"
    assert body["storage_path"].startswith(f"{USER_A}/")
    assert len(body["pages"]) == 2
    assert body["pages"][0]["classification"] == "digital"
    assert len(body["sha256"]) == 64
    assert body["issues"] == []
    assert len(fake_client.tables["documents"]) == 1
    assert len(fake_client.tables["jobs"]) == 1


def test_upload_same_file_replays_no_duplicate(client, fake_client):
    data = _pdf()
    first = _upload(client, "token-user-a", "paper-66.pdf", data)
    assert first.status_code == 200
    second = _upload(client, "token-user-a", "paper-66-copy.pdf", data)
    assert second.status_code == 200
    body = second.json()
    assert body["status"] == "replay"
    assert body["idempotent_replay"] is True
    assert body["document"]["id"] == first.json()["document"]["id"]
    assert len(fake_client.tables["documents"]) == 1
    assert len(fake_client.tables["jobs"]) == 1


def test_upload_same_file_other_user_is_separate(client, fake_client):
    data = _pdf()
    _upload(client, "token-user-a", "paper.pdf", data)
    res = _upload(client, "token-user-b", "paper.pdf", data)
    assert res.status_code == 200
    assert res.json()["status"] == "stored"  # dedup is per user, never cross-user
    assert len(fake_client.tables["documents"]) == 2


def test_upload_image_scanned_page(client):
    res = _upload(client, "token-user-a", "scan.png", _png(), mime="image/png")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "stored"
    assert len(body["pages"]) == 1
    assert body["pages"][0]["classification"] == "scanned"
    assert body["pages"][0]["width_px"] == 800


def test_upload_rejects_fake_pdf(client, fake_client):
    res = _upload(client, "token-user-a", "fake.pdf", b"hello, not a pdf")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "magic_bytes_mismatch"
    assert len(fake_client.tables["documents"]) == 0


def test_upload_rejects_encrypted_pdf(client, fake_client):
    res = _upload(client, "token-user-a", "locked.pdf", _pdf(encrypted=True))
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "pdf_encrypted"
    assert len(fake_client.tables["documents"]) == 0


def test_upload_rejects_oversize(client, fake_client, monkeypatch):
    monkeypatch.setattr(settings, "max_file_size_bytes", 10)
    res = _upload(client, "token-user-a", "paper.pdf", _pdf())
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "file_too_large"


def test_upload_requires_auth(client):
    res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("paper.pdf", _pdf(), "application/pdf")},
    )
    assert res.status_code == 401


def test_batch_mixed_results(client, fake_client):
    res = client.post(
        "/api/v1/documents/upload/batch",
        files=[
            ("files", ("good.pdf", _pdf(), "application/pdf")),
            ("files", ("bad.pdf", b"junk bytes", "application/pdf")),
            ("files", ("scan.png", _png(), "image/png")),
        ],
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["stored"] == 2
    assert body["rejected"] == 1
    assert body["replayed"] == 0
    statuses = {r["filename"]: r["status"] for r in body["results"]}
    assert statuses == {"good.pdf": "stored", "bad.pdf": "rejected", "scan.png": "stored"}
    bad = next(r for r in body["results"] if r["filename"] == "bad.pdf")
    assert bad["issues"][0]["code"] == "magic_bytes_mismatch"
    assert len(fake_client.tables["documents"]) == 2


def test_batch_too_many_files(client):
    files = [("files", (f"f{i}.txt", b"x", "text/plain")) for i in range(21)]
    res = client.post(
        "/api/v1/documents/upload/batch",
        files=files,
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "batch_too_large"


def test_batch_requires_auth(client):
    res = client.post(
        "/api/v1/documents/upload/batch",
        files=[("files", ("a.txt", b"x", "text/plain"))],
    )
    assert res.status_code == 401


def test_register_still_accepts_webp_file_type(client):
    # FileType enum gained webp/tiff in M1; register validates them.
    payload = register_payload(USER_A, file_type="webp", storage_path=f"{USER_A}/a.webp")
    res = client.post(
        "/api/v1/documents/register", json=payload, headers=auth_headers("token-user-a")
    )
    assert res.status_code in (200, 201), res.text
