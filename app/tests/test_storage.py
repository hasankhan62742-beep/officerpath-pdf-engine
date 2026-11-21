# OfficerPath AI — PDF Engine (Phase 1, M1) — tests
# StorageBackend: local-disk implementation. Immutability,
# traversal protection, safe generated names.

import pytest

from app.storage.base import assert_safe_relative_path, safe_storage_name
from app.storage.local import LocalDiskStorage


def test_put_get_exists_delete(tmp_path):
    store = LocalDiskStorage(str(tmp_path))
    path = "user-1/abc.pdf"
    assert store.exists(path) is False
    assert store.put(path, b"%PDF-") == path
    assert store.exists(path) is True
    assert store.get(path) == b"%PDF-"
    store.delete(path)
    assert store.exists(path) is False


def test_put_refuses_overwrite(tmp_path):
    store = LocalDiskStorage(str(tmp_path))
    store.put("user-1/a.pdf", b"v1")
    with pytest.raises(FileExistsError):
        store.put("user-1/a.pdf", b"v2")
    assert store.get("user-1/a.pdf") == b"v1"


def test_get_missing_raises(tmp_path):
    store = LocalDiskStorage(str(tmp_path))
    with pytest.raises(FileNotFoundError):
        store.get("user-1/nope.pdf")


def test_delete_missing_is_noop(tmp_path):
    store = LocalDiskStorage(str(tmp_path))
    store.delete("user-1/nope.pdf")  # must not raise


def test_traversal_rejected(tmp_path):
    store = LocalDiskStorage(str(tmp_path))
    for bad in ("../escape.pdf", "a/../../escape.pdf", "/etc/passwd"):
        with pytest.raises(ValueError):
            store.put(bad, b"x")
        with pytest.raises(ValueError):
            store.get(bad)


def test_safe_storage_name():
    path = safe_storage_name("user-1", "../../my paper (1).pdf")
    assert path.startswith("user-1/")
    assert ".." not in path
    assert "/" not in path.split("/", 1)[1]
    assert path.endswith(".pdf")
    # Two calls never collide (UUID prefix).
    assert safe_storage_name("user-1", "a.pdf") != safe_storage_name("user-1", "a.pdf")


def test_assert_safe_relative_path(tmp_path):
    ok = assert_safe_relative_path(str(tmp_path), "a/b.pdf")
    assert ok.endswith("a/b.pdf")
    with pytest.raises(ValueError):
        assert_safe_relative_path(str(tmp_path), "../evil.pdf")
