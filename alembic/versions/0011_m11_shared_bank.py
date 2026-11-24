# OfficerPath AI — PDF Engine (Phase 2, M11)
"""M11: shared question bank — ``documents.is_shared``.

Revision ID: 0011_m11_shared_bank
Revises: 0010_m10_explanations
Create Date: 2026-11-24

Owner rule: students must be able to take tests from the
admin-owned question bank. Until now the M6 test pool joined
``documents`` and filtered ``user_id == caller``, so a student
could NEVER get questions from an admin-owned bank document.

- ``documents.is_shared``: False by default. An admin marks a
  bank document shared (PATCH /api/v1/admin/documents/{id}/
  sharing); students then read its questions (read-only) in
  the test pool — their own documents plus every shared one.
  Private documents stay visible only to their owner.

Additive-only, NOT NULL with server default false: existing
rows are unaffected. Downgrade drops the column.

The add/drop are guarded by a column-exists check: the
schema tests pre-create ``documents`` from the models (which
already carry ``is_shared``) before running ``upgrade head``,
so a blind add_column would fail with "duplicate column
name". The guard makes the revision safe on both paths —
migration-built tables and model-built tables.

LIVE APPLY: this Alembic revision covers fresh/local DBs
built by ``alembic upgrade head``. The live Supabase table
is owned by migration 015, so the same column is added live
by supabase/migrations/020_documents_is_shared.sql (SQL
Editor, owner go-ahead) — the 019 precedent.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0011_m11_shared_bank"
down_revision = "0010_m10_explanations"
branch_labels = None
depends_on = None


def _has_column(bind: object, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}  # type: ignore[arg-type]


def upgrade() -> None:
    bind = op.get_bind()
    if bind is not None and not _has_column(bind, "documents", "is_shared"):
        op.add_column(
            "documents",
            sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind is not None and _has_column(bind, "documents", "is_shared"):
        op.drop_column("documents", "is_shared")
