# OfficerPath AI — PDF Engine (Phase 1, M1)
# Alembic environment. Reads the target URL from app settings
# (DATABASE_URL env var) — never from a committed file.
# Online migrations only; offline mode is unsupported by design
# (the migration must run against a real database to be verified).

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings  # noqa: E402
from app.db.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False: fileConfig's default (True) disables
    # every logger created before this call — in tests that silently
    # killed app.main's request log for the rest of the process, so
    # test_observability failed whenever a migration test ran first
    # (M7: test_exam.py sorts before it; M6's migration tests only
    # escaped it because test_tests.py sorts after). Alembic still
    # configures its own loggers from the ini.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    url = settings.database_url
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Set it to the SQLAlchemy URL of the "
            "Supabase Postgres database (postgresql+psycopg://...) or, for "
            "local migration tests only, a SQLite file URL."
        )
    return url


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
