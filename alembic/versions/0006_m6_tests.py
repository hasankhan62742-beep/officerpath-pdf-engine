# OfficerPath AI — PDF Engine (Phase 2, M6)
"""M6: test builder tables + the documents/jobs carry-over fix.

Revision ID: 0006_m6_tests
Revises: 0005_m5_subjects
Create Date: 2026-11-22

Two jobs in one revision (both are M6 scope — see the M6 report):

1. TEST BUILDER (doc 03 §2.4): creates ``marking_configs``,
   ``test_templates``, ``test_sessions`` and
   ``test_question_snapshots`` and seeds the PPSC default marking
   config (+1 / −0.25 / 0, is_default). The seed is idempotent
   (ON CONFLICT DO NOTHING on Postgres, INSERT OR IGNORE on
   SQLite) so re-running the revision never duplicates it.

2. DOCUMENTS/JOBS CARRY-OVER (M5 §5.2, recorded repo gap):
   Alembic 0001 assumes Supabase migration 015 already created
   the ``documents`` and ``jobs`` tables ("015 owns them"), so a
   fresh database built by ``alembic upgrade head`` alone had
   NEITHER table — the worker failed with ``no such table: jobs``
   and no upload could complete. Tests never caught it
   (conftest uses ``create_all``) and the M4/M5 harnesses worked
   around it with ``create_all`` after the upgrade.
   This revision creates ``documents`` and ``jobs`` IF THEY DO
   NOT ALREADY EXIST, mirroring the 015 DDL (same columns,
   checks, and unique indexes) so a fresh Alembic-only database
   upgrades to head and the worker starts. On a database where
   015 already applied, both tables exist and this step is a
   no-op — it never alters, drops, or rewrites an existing
   table. The live Supabase tables stay 015-owned; Alembic only
   guarantees their presence for engine-managed databases.
   ONE deliberate divergence from 015: the (user_id,
   content_hash) unique index is PARTIAL (``WHERE deleted_at
   IS NULL``) — see ``_create_documents_if_missing``. 015's
   plain unique index breaks delete-then-re-upload (500); the
   live table gets the same fix via Supabase migration 017.

Deviations from doc 03 §2.4 (recorded, not silent):
- ``test_templates.question_count`` has NO CHECK IN
  (25, 50, 100, 150, 200): the M6 brief's E2E proof builds a
  20-question test, and the range is enforced in the service
  layer (1–200) instead. The UI still offers 25/50/100/150/200
  as quick picks.
- ``test_sessions.server_started_at`` is NULLABLE in M6: no exam
  has started yet (M7 sets it at start, never from the browser
  clock). Doc 03 marks it NOT NULL; M7 will enforce it when the
  exam flow exists.

Downgrade: refuses while ``test_sessions`` or
``test_templates`` hold user rows (doc 03 §6 — a downgrade never
deletes user data silently). It drops only the four M6 tables;
``documents``/``jobs`` are NEVER dropped by this downgrade —
they are 015-owned (or pre-existing) and may hold user data.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa

from alembic import op

revision = "0006_m6_tests"
down_revision = "0005_m5_subjects"
branch_labels = None
depends_on = None

JSONVariant = sa.JSON().with_variant(sa.JSON(), "sqlite")

#: The PPSC default marking scheme (Phase 2 prompt §24): correct
#: +1, incorrect −0.25, unattempted 0. Seeded once, idempotently.
PPSC_DEFAULT_NAME = "PPSC default"


def _has_table(bind: object, name: str) -> bool:
    return sa.inspect(bind).has_table(name)  # type: ignore[arg-type]


def _create_documents_if_missing() -> bool:
    """Create the 015-mirror ``documents`` table when absent.

    Returns True when the table was created. Mirrors
    supabase/migrations/015_documents_jobs.sql (a) — same
    columns, checks, and unique indexes. The ``user_id →
    auth.users`` foreign key is deliberately NOT mirrored: it
    only exists on the live Supabase Postgres, and the engine
    never relies on it (ownership is enforced in code, JWT user
    id only)."""
    bind = op.get_bind()
    if bind is None or _has_table(bind, "documents"):
        return False
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("user_id", sa.Uuid, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("storage_path", sa.Text, nullable=False),
        sa.Column("file_type", sa.String(16), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=False),
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("metadata", JSONVariant, nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "file_type IN ('pdf', 'txt', 'docx', 'jpg', 'jpeg', 'png', 'webp', 'tiff', 'tif')",
            name="documents_file_type_check",
        ),
        sa.CheckConstraint("file_size_bytes > 0", name="documents_file_size_check"),
        sa.CheckConstraint(
            "page_count IS NULL OR (page_count BETWEEN 1 AND 100)",
            name="documents_page_count_check",
        ),
        sa.CheckConstraint(
            "content_hash IS NULL OR length(content_hash) = 64",
            name="documents_content_hash_check",
        ),
        sa.UniqueConstraint("user_id", "storage_path", name="documents_user_storage_path_key"),
    )
    op.create_index(
        "documents_user_created_idx", "documents", ["user_id", "created_at"], unique=False
    )
    # M6 fix (found by measuring in the M6 E2E): the 015 mirror
    # originally carried a PLAIN unique index on (user_id,
    # content_hash). The dedup lookup ignores soft-deleted rows
    # (M4), but the plain index does not — delete-then-re-upload
    # of the same file failed with 500 UNIQUE constraint failed.
    # The index is therefore PARTIAL (live rows only), so a
    # deleted row never blocks a fresh upload of the same file,
    # while two live rows with the same hash still cannot exist.
    # This deliberately diverges from 015's DDL; Supabase
    # migration 017 carries the same change for the live table
    # (017 is written, not applied — owner step).
    op.create_index(
        "documents_user_hash_idx",
        "documents",
        ["user_id", "content_hash"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    return True


def _create_jobs_if_missing() -> bool:
    """Create the 015-mirror ``jobs`` table when absent.

    Returns True when the table was created. Mirrors
    supabase/migrations/015_documents_jobs.sql (b)."""
    bind = op.get_bind()
    if bind is None or _has_table(bind, "jobs"):
        return False
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("user_id", sa.Uuid, nullable=False),
        sa.Column("document_id", sa.Uuid, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("result_summary", JSONVariant, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('queued', 'uploading', 'processing', 'done', 'failed', 'cancelled')",
            name="jobs_status_check",
        ),
        sa.CheckConstraint("retry_count >= 0", name="jobs_retry_count_check"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="jobs_user_idempotency_key"),
    )
    op.create_index("jobs_user_created_idx", "jobs", ["user_id", "created_at"], unique=False)
    op.create_index("jobs_active_idx", "jobs", ["status"], unique=False)
    return True


def upgrade() -> None:
    # Part 1 — carry-over: documents/jobs must exist before any
    # table that references them, and before the worker can run.
    # No-op on databases where 015 already applied.
    _create_documents_if_missing()
    _create_jobs_if_missing()

    # Part 2 — the M6 test-builder tables (doc 03 §2.4).
    op.create_table(
        "marking_configs",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("correct_marks", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("incorrect_marks", sa.Float, nullable=False, server_default="-0.25"),
        sa.Column("unattempted_marks", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "test_templates",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("user_id", sa.Uuid, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("question_count", sa.Integer, nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_ids", JSONVariant, nullable=True),
        sa.Column("allow_repetition", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("include_unknown", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("selection_seed", sa.Integer, nullable=True),
        sa.Column("excluded_unknown", sa.Integer, nullable=False, server_default="0"),
        sa.Column("excluded_no_options", sa.Integer, nullable=False, server_default="0"),
        sa.Column("marking_config_id", sa.Uuid, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["marking_config_id"], ["marking_configs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_test_templates_user_created", "test_templates", ["user_id", "created_at"])
    op.create_table(
        "test_sessions",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("user_id", sa.Uuid, nullable=False),
        sa.Column("template_id", sa.Uuid, nullable=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("question_count", sa.Integer, nullable=False),
        sa.Column("marking_config_id", sa.Uuid, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="created"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_limit_seconds", sa.Integer, nullable=True),
        sa.Column("server_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["template_id"], ["test_templates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["marking_config_id"], ["marking_configs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_test_sessions_user_created", "test_sessions", ["user_id", "created_at"])
    op.create_table(
        "test_question_snapshots",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("session_id", sa.Uuid, nullable=False),
        sa.Column("question_id", sa.Uuid, nullable=True),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("question_text", sa.Text, nullable=False),
        sa.Column("options", JSONVariant, nullable=False),
        sa.Column("correct_index", sa.Integer, nullable=False),
        sa.Column("answer_source", sa.String(64), nullable=True),
        sa.Column("source_document_id", sa.Uuid, nullable=True),
        sa.Column("source_page", sa.Integer, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["session_id"], ["test_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["extracted_questions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "position", name="ix_snapshots_session_position"),
    )
    op.create_index("ix_snapshots_session", "test_question_snapshots", ["session_id", "created_at"])

    # Idempotent seed: the PPSC default marking config.
    # NOTE (2026-11-23, live-Postgres run): bind the id as a uuid
    # object with type_=sa.Uuid — a plain hex str binds as VARCHAR
    # and Postgres rejects varchar -> uuid in this INSERT (same bug
    # as 0005's subject seed). Typed Uuid stores CHAR(32) hex on
    # SQLite and native uuid on Postgres.
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else "postgresql"
    if dialect == "sqlite":
        op.execute(
            sa.text(
                "INSERT OR IGNORE INTO marking_configs "
                "(id, name, correct_marks, incorrect_marks, unattempted_marks, is_default) "
                "VALUES (:id, :name, 1.0, -0.25, 0.0, 1)"
            ).bindparams(
                sa.bindparam("id", type_=sa.Uuid, value=uuid.uuid4()),
                name=PPSC_DEFAULT_NAME,
            )
        )
    else:
        op.execute(
            sa.text(
                "INSERT INTO marking_configs "
                "(id, name, correct_marks, incorrect_marks, unattempted_marks, is_default) "
                "VALUES (:id, :name, 1.0, -0.25, 0.0, true) ON CONFLICT (name) DO NOTHING"
            ).bindparams(
                sa.bindparam("id", type_=sa.Uuid, value=uuid.uuid4()),
                name=PPSC_DEFAULT_NAME,
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    sessions = 0
    templates = 0
    if bind is not None:
        sessions = int(bind.execute(sa.text("SELECT COUNT(*) FROM test_sessions")).scalar() or 0)
        templates = int(bind.execute(sa.text("SELECT COUNT(*) FROM test_templates")).scalar() or 0)
    if sessions > 0 or templates > 0:
        raise RuntimeError(
            f"Refusing downgrade: test_sessions holds {sessions} session(s) and "
            f"test_templates holds {templates} template(s). Archive them first — "
            "a downgrade never deletes user data silently (doc 03 §6)."
        )
    op.drop_index("ix_snapshots_session", table_name="test_question_snapshots")
    op.drop_table("test_question_snapshots")
    op.drop_index("ix_test_sessions_user_created", table_name="test_sessions")
    op.drop_table("test_sessions")
    op.drop_index("ix_test_templates_user_created", table_name="test_templates")
    op.drop_table("test_templates")
    op.drop_table("marking_configs")
    # documents/jobs are deliberately NOT dropped here: they are
    # 015-owned (or pre-existing) and may hold user data.
