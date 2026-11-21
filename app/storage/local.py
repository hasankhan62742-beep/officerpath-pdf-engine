# OfficerPath AI — PDF Engine (Phase 1, M1)
# Local-disk StorageBackend. Development / Stage-1 default only:
# Render's filesystem is ephemeral, so local storage must NOT be
# treated as durable production persistence (see docs/deploy-render.md
# — the durable home for originals on Render is the Supabase
# `pdf-documents` bucket; local storage is for local runs and tests).

from __future__ import annotations

from pathlib import Path

from app.storage.base import assert_safe_relative_path


class LocalDiskStorage:
    """Write-once local storage rooted at `root`."""

    def __init__(self, root: str) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, path: str) -> Path:
        return Path(assert_safe_relative_path(str(self._root), path))

    def put(self, path: str, data: bytes) -> str:
        target = self._resolve(path)
        if target.exists():
            raise FileExistsError(f"Refusing to overwrite stored original: {path!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp sibling then rename: no partial originals.
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(target)
        return path

    def get(self, path: str) -> bytes:
        target = self._resolve(path)
        if not target.is_file():
            raise FileNotFoundError(f"No stored object: {path!r}")
        return target.read_bytes()

    def exists(self, path: str) -> bool:
        return self._resolve(path).is_file()

    def delete(self, path: str) -> None:
        target = self._resolve(path)
        if target.is_file():
            target.unlink()
