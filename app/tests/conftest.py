# OfficerPath AI — PDF Engine (Phase 1A) — tests
# In-memory fake of the small Supabase surface the app uses:
# client.table(name).select/insert/update .eq(...).limit(n).execute()
# and client.auth.get_user(token). No network, no live Supabase.

import copy
import os

# Dummy Supabase config for tests — set BEFORE importing the app, so
# Settings reads them at import time. These are fake values; no real
# Supabase is ever contacted (the fake client below is used instead).
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security.rate_limit import rate_limiter

USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeUser:
    def __init__(self, user_id, email=None):
        self.id = user_id
        self.email = email or f"{user_id}@example.com"


class _FakeUserResponse:
    def __init__(self, user):
        self.user = user


class _FakeAuth:
    def __init__(self, tokens):
        self._tokens = tokens  # token -> user_id

    def get_user(self, token):
        user_id = self._tokens.get(token)
        if user_id is None:
            raise Exception("invalid token")
        return _FakeUserResponse(_FakeUser(user_id))


class _FakeTable:
    def __init__(self, store):
        self._store = store  # list of row dicts
        self._filters = []
        self._limit = None
        self._op = None
        self._payload = None

    def select(self, *args, **kwargs):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _matches(self, row):
        return all(row.get(col) == val for col, val in self._filters)

    def execute(self):
        if self._op == "insert":
            row = copy.deepcopy(self._payload)
            self._store.append(row)
            return _FakeResponse([copy.deepcopy(row)])
        rows = [r for r in self._store if self._matches(r)]
        if self._op == "update":
            for row in rows:
                row.update(copy.deepcopy(self._payload))
            return _FakeResponse([copy.deepcopy(r) for r in rows])
        if self._limit is not None:
            rows = rows[: self._limit]
        return _FakeResponse([copy.deepcopy(r) for r in rows])


class FakeSupabaseClient:
    """Minimal fake: tables 'documents' and 'jobs', plus auth tokens."""

    def __init__(self):
        self.tables = {"documents": [], "jobs": []}
        self.auth = _FakeAuth({"token-user-a": USER_A, "token-user-b": USER_B})

    def table(self, name):
        return _FakeTable(self.tables[name])


@pytest.fixture()
def fake_client():
    return FakeSupabaseClient()


@pytest.fixture()
def client(fake_client):
    rate_limiter.reset()
    # Enter the TestClient first (lifespan runs and sets real clients),
    # then override app.state with the fake — lifespan must not win.
    with TestClient(app) as test_client:
        app.state.supabase_client = fake_client
        app.state.service_client = fake_client
        yield test_client
    app.state.supabase_client = None
    app.state.service_client = None


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register_payload(user_id: str, **overrides) -> dict:
    payload = {
        "title": "Model Paper 66",
        "storage_path": f"{user_id}/paper-66.pdf",
        "file_type": "pdf",
        "file_size_bytes": 5_900_000,
        "page_count": 7,
        "idempotency_key": "key-1",
    }
    payload.update(overrides)
    return payload
