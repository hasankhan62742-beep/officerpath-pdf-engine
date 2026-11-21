# OfficerPath AI — PDF Engine (Phase 1, M1)
# SQLAlchemy engine + session factory for the engine-owned tables.
#
# The engine is created lazily and only when DATABASE_URL is configured
# (settings.database_configured). Without it the API still serves the
# PostgREST register/jobs flow; stage history is then recorded by the
# NullStageRecorder (in-memory, per-request) instead of the database.
# Connection pooling is deliberately small: Render free is 512 MB /
# 0.1 CPU (ADR-001) and Supabase free Postgres caps connections, so
# pool_size=2 / max_overflow=2 is the M1 default. Tune in M7 with
# measured load-test numbers, not guesses.

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine | None:
    """Return the shared engine, or None when DATABASE_URL is unset."""
    global _engine, _session_factory
    if _engine is not None:
        return _engine
    if not settings.database_configured or settings.database_url is None:
        return None
    _engine = create_engine(
        settings.database_url,
        pool_size=2,
        max_overflow=2,
        pool_pre_ping=True,
        future=True,
    )
    _session_factory = sessionmaker(bind=_engine, autoflush=False, future=True)
    return _engine


def get_session() -> Session | None:
    """Return a new session, or None when DATABASE_URL is unset."""
    if get_engine() is None or _session_factory is None:
        return None
    return _session_factory()


def reset_engine_for_tests() -> None:
    """Drop the cached engine (tests only — never call in production)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
