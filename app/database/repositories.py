# OfficerPath AI — PDF Engine (Phase 1A)
# Repositories for the two new tables (migration 015): `documents` and
# `jobs`. They speak to Supabase through the client's PostgREST interface
# only — no raw SQL, no access to any pre-existing table. The backend
# NEVER reads or writes profiles / activation_codes / payments /
# test_results / waitlist / sent_notifications / redeem_attempts.
#
# The repositories generate ids/timestamps in Python so behaviour is
# identical against the real client and against the in-memory fake used
# in tests (see app/tests/conftest.py).

import uuid
from datetime import UTC, datetime
from typing import Any

JOB_STATUSES = ("queued", "uploading", "processing", "done", "failed", "cancelled")
RETRYABLE_STATUSES = ("failed", "cancelled")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class DocumentRepository:
    def __init__(self, client: Any) -> None:
        self._client = client

    def find_by_user_and_path(self, user_id: str, storage_path: str) -> dict | None:
        res = (
            self._client.table("documents")
            .select("*")
            .eq("user_id", user_id)
            .eq("storage_path", storage_path)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else None

    def find_by_user_and_sha256(self, user_id: str, sha256: str) -> dict | None:
        """SHA-256 dedup lookup (M1 ingestion). Per user only — never
        reveal another user's file. Returns None until migration 015
        (revised, M1) is applied live, because the content_hash column
        does not exist before then; callers treat None as "no match"."""
        res = (
            self._client.table("documents")
            .select("*")
            .eq("user_id", user_id)
            .eq("content_hash", sha256)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else None

    def create(self, data: dict) -> dict:
        row = {"id": str(uuid.uuid4()), "created_at": _now_iso(), **data}
        res = self._client.table("documents").insert(row).execute()
        return dict((res.data or [row])[0])


class JobRepository:
    def __init__(self, client: Any) -> None:
        self._client = client

    def find_by_id(self, job_id: str) -> dict | None:
        res = self._client.table("jobs").select("*").eq("id", job_id).limit(1).execute()
        rows = res.data or []
        return rows[0] if rows else None

    def find_by_user_and_idempotency_key(self, user_id: str, idempotency_key: str) -> dict | None:
        res = (
            self._client.table("jobs")
            .select("*")
            .eq("user_id", user_id)
            .eq("idempotency_key", idempotency_key)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else None

    def find_by_document_id(self, document_id: str) -> dict | None:
        res = (
            self._client.table("jobs").select("*").eq("document_id", document_id).limit(1).execute()
        )
        rows = res.data or []
        return rows[0] if rows else None

    def create(self, data: dict) -> dict:
        row = {
            "id": str(uuid.uuid4()),
            "status": "queued",
            "retry_count": 0,
            "created_at": _now_iso(),
            **data,
        }
        res = self._client.table("jobs").insert(row).execute()
        return dict((res.data or [row])[0])

    def update(self, job_id: str, data: dict) -> dict | None:
        res = self._client.table("jobs").update(data).eq("id", job_id).execute()
        rows = res.data or []
        return rows[0] if rows else None
