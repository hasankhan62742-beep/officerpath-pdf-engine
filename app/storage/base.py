# OfficerPath AI — PDF Engine (Phase 1, M1)
# StorageBackend interface + safe-name helpers.
#
# Rules (prompt §6/§18): generated safe names (never the user's raw
# filename as a path), no path traversal, originals immutable
# (put() refuses to overwrite), one backend behind the interface.

from __future__ import annotations

import re
import uuid
from typing import Protocol

_SAFE_SEGMENT = re.compile(r"[^A-Za-z0-9._-]+")


def safe_storage_name(user_id: str, filename: str) -> str:
    """Build a storage path `<user_id>/<uuid>-<sanitized-name>`.

    The original filename is metadata only: it is sanitized to one
    safe segment (no slashes, no `..`, no whitespace) and prefixed
    with a UUID so two uploads can never collide.
    """
    base = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    base = _SAFE_SEGMENT.sub("_", base).strip("._") or "file"
    base = base[:100]
    return f"{user_id}/{uuid.uuid4()}-{base}"


def assert_safe_relative_path(root: str, path: str) -> str:
    """Resolve `path` under `root`; raise ValueError on traversal."""
    from pathlib import Path

    root_path = Path(root).resolve()
    target = (root_path / path).resolve()
    if target != root_path and root_path not in target.parents:
        raise ValueError(f"Unsafe storage path: {path!r}")
    return str(target)


class StorageBackend(Protocol):
    """Object-storage interface. Implementations: local disk (M1),
    S3-compatible (later milestone)."""

    def put(self, path: str, data: bytes) -> str:
        """Store bytes at `path`. Refuses to overwrite (immutability).
        Returns the stored path. Raises FileExistsError on overwrite."""
        ...

    def get(self, path: str) -> bytes:
        """Read bytes. Raises FileNotFoundError when absent."""
        ...

    def exists(self, path: str) -> bool: ...

    def delete(self, path: str) -> None:
        """Delete (service-side cleanup only; clients have no delete).
        No-op when absent."""
        ...
