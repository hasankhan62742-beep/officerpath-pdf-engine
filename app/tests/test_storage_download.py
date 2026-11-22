# OfficerPath AI — Phase 2, M4
# download_bucket_bytes proofs against fake service clients
# (no network, no live Supabase — the function only ever talks
# to the client it is given).

import pytest

from app.core.errors import ApiError
from app.integrations.supabase_storage import download_bucket_bytes


class _FakeBucket:
    def __init__(self, behaviour):
        self._behaviour = (
            behaviour  # "ok" | "bucket-missing" | "object-missing" | "boom" | "not-bytes"
        )

    def download(self, path):
        if self._behaviour == "ok":
            return b"%PDF-1.4 fake-bytes"
        if self._behaviour == "bucket-missing":
            raise Exception("Bucket not found")
        if self._behaviour == "object-missing":
            raise Exception("Object not found")
        if self._behaviour == "not-bytes":
            return {"signedURL": "https://example.invalid/x"}
        raise Exception("boom")


class _FakeStorage:
    def __init__(self, behaviour):
        self._behaviour = behaviour

    def from_(self, bucket):
        assert bucket == "pdf-documents"
        return _FakeBucket(self._behaviour)


class _FakeServiceClient:
    def __init__(self, behaviour):
        self.storage = _FakeStorage(behaviour)


def test_download_returns_bytes():
    data = download_bucket_bytes(
        "pdf-documents", "user/file.pdf", service_client=_FakeServiceClient("ok")
    )
    assert data == b"%PDF-1.4 fake-bytes"


def test_download_no_service_client_is_503(monkeypatch):
    import app.integrations.supabase_storage as mod

    monkeypatch.setattr(mod, "get_service_client", lambda: None)
    with pytest.raises(ApiError) as excinfo:
        download_bucket_bytes("pdf-documents", "user/file.pdf")
    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "storage_unavailable"


def test_download_missing_bucket_names_the_fix():
    with pytest.raises(ApiError) as excinfo:
        download_bucket_bytes(
            "pdf-documents", "user/file.pdf", service_client=_FakeServiceClient("bucket-missing")
        )
    assert excinfo.value.code == "storage_bucket_missing"
    assert "016" in excinfo.value.message


def test_download_missing_object_is_distinct():
    with pytest.raises(ApiError) as excinfo:
        download_bucket_bytes(
            "pdf-documents", "user/file.pdf", service_client=_FakeServiceClient("object-missing")
        )
    assert excinfo.value.code == "storage_object_missing"


def test_download_other_failures_are_generic():
    with pytest.raises(ApiError) as excinfo:
        download_bucket_bytes(
            "pdf-documents", "user/file.pdf", service_client=_FakeServiceClient("boom")
        )
    assert excinfo.value.code == "storage_error"
    assert "boom" not in excinfo.value.message


def test_download_non_bytes_response_is_an_error():
    with pytest.raises(ApiError) as excinfo:
        download_bucket_bytes(
            "pdf-documents", "user/file.pdf", service_client=_FakeServiceClient("not-bytes")
        )
    assert excinfo.value.code == "storage_error"
