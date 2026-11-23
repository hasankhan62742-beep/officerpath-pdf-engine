# OfficerPath AI — regression test (2026-11-23).
#
# The first Render deploy failed because the Supabase pooler URL uses
# the plain postgresql:// scheme, which SQLAlchemy maps to the psycopg2
# dialect — not installed (requirements pin psycopg v3 only). /health
# then raised ModuleNotFoundError: psycopg2 and the health check timed
# out. Settings must rewrite bare Postgres schemes to
# postgresql+psycopg:// at construction.

from app.config import Settings


def test_plain_postgresql_url_rewritten_to_psycopg():
    s = Settings(database_url="postgresql://u:p@host:5432/db")
    assert s.database_url == "postgresql+psycopg://u:p@host:5432/db"


def test_postgres_scheme_rewritten_to_psycopg():
    s = Settings(database_url="postgres://u:p@host:5432/db")
    assert s.database_url == "postgresql+psycopg://u:p@host:5432/db"


def test_qualified_url_unchanged():
    s = Settings(database_url="postgresql+psycopg://u:p@host:5432/db")
    assert s.database_url == "postgresql+psycopg://u:p@host:5432/db"


def test_sqlite_url_unchanged():
    s = Settings(database_url="sqlite:////tmp/officerpath-test.db")
    assert s.database_url == "sqlite:////tmp/officerpath-test.db"


def test_no_url_stays_none(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert Settings().database_url is None


def test_engine_creation_with_plain_url_uses_psycopg(monkeypatch):
    """End to end at the session layer: a plain Supabase-style URL
    must build an engine on the psycopg driver, not raise
    ModuleNotFoundError: psycopg2. The host is unreachable on
    purpose — create_engine does not connect, so this stays offline."""
    import app.db.session as session_mod

    fresh = Settings(database_url="postgresql://bad:bad@127.0.0.1:1/db")
    monkeypatch.setattr(session_mod, "settings", fresh)
    try:
        engine = session_mod.get_engine()
        assert engine is not None
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.dialect.driver == "psycopg"
    finally:
        session_mod.reset_engine_for_tests()
