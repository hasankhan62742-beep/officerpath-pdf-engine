# OfficerPath AI — PDF Engine (Phase 1A) — tests
# In-memory fake of the small Supabase surface the app uses:
# client.auth.get_user(token). No network, no live Supabase.
#
# ADR-011 (M3): the engine DB is the single access path for
# documents + jobs, so the fake no longer emulates PostgREST
# tables — tests that need documents/jobs use the `engine_db`
# fixture (throwaway SQLite) instead.

import os

# Dummy Supabase config for tests — set BEFORE importing the app, so
# Settings reads them at import time. These are fake values; no real
# Supabase is ever contacted (the fake client below is used instead).
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.v1.async_jobs as async_jobs_api
import app.api.v1.me as me_api
import app.api.v1.review as review_api
import app.api.v1.routes as routes_api
from app.config import settings
from app.db.models import Base
from app.main import app
from app.security.rate_limit import rate_limiter

USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"


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
    """Health-probe stub only (ADR-011): the /health endpoint probes
    the Supabase client with
    ``client.table("documents").select("id").limit(1).execute()``.
    This stub answers that chain with empty rows so the probe can
    verify the client object is usable. It is NOT a PostgREST
    emulation — documents/jobs live in the engine DB now, and no
    test may use this stub as a data store (use engine_db)."""

    def select(self, *args, **kwargs):
        return self

    def limit(self, n):
        return self

    def execute(self):
        return _FakeResponse([])


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeSupabaseClient:
    """Minimal fake: auth tokens + the health-probe table stub
    (ADR-011 — the engine DB owns documents/jobs now; use the
    engine_db fixture for those)."""

    def __init__(self):
        self.auth = _FakeAuth({"token-user-a": USER_A, "token-user-b": USER_B})

    def table(self, name):
        return _FakeTable()


@pytest.fixture()
def fake_client():
    return FakeSupabaseClient()


@pytest.fixture()
def engine_db(tmp_path, monkeypatch):
    """Throwaway SQLite engine DB (all tables) + the API modules'
    get_session patched to it, so register/upload/jobs/profile
    endpoints run against the same store the async-jobs path uses
    (ADR-011 unification proof lives in test_job_store_unification).
    Yields the session factory for direct row assertions."""
    engine = create_engine(f"sqlite:///{tmp_path}/engine.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(routes_api, "get_session", lambda: factory())
    monkeypatch.setattr(me_api, "get_session", lambda: factory())
    monkeypatch.setattr(async_jobs_api, "get_session", lambda: factory())
    monkeypatch.setattr(review_api, "get_session", lambda: factory())
    monkeypatch.setattr(settings, "storage_root", str(tmp_path / "storage"))
    yield factory
    engine.dispose()


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
