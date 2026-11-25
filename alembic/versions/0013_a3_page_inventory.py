# OfficerPath AI — PDF Engine (A3)
"""A3: page inventory columns on ``document_pages``.

Revision ID: 0013_a3_page_inventory
Revises: 0012_m16_community_questions
Create Date: 2026-11-25

Gap-report F7: the pipeline recorded per-page classification at
ingest but never what extraction found on each page. These three
additive columns hold the inventory the worker records after a
parse (see app/services/pages.py):

- ``extraction_status``: processed | no_questions | failed |
  low_confidence (NULL = never inventoried, e.g. parsed before
  A3). No DB CHECK on the values — the service layer is the only
  writer and validates them; a CHECK would need a constraint
  name lookup to stay guarded on both paths.
- ``question_count``: stored question rows (MCQs + pending)
  attributed to the page.
- ``error_message``: short reason when status is "failed"
  (a code / page number only — never file contents or OCR text).

Additive-only. Downgrade drops the three columns (the
inventory is derived data — it can be rebuilt by re-parsing).

Guards (the 0011/0012 precedent): the schema tests pre-create
all tables from the models before running ``upgrade head``, so
a blind add_column would fail with "already exists". Every
step checks first, making the revision safe on both paths —
migration-built tables and model-built tables.

LIVE APPLY: this Alembic revision covers fresh/local DBs built
by ``alembic upgrade head``. The live Supabase tables are owned
by migration 015, so the same columns are added live by
supabase/migrations/022_document_pages_inventory.sql (SQL
Editor, owner go-ahead) — the 019/020/021 precedent. The
expected question count needs NO migration: it lives in
Document.metadata (JSONB).
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0013_a3_page_inventory"
down_revision = "0012_m16_community_questions"
branch_labels = None
depends_on = None


def _has_column(bind: object, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}  # type: ignore[arg-type]


def upgrade() -> None:
    bind = op.get_bind()
    if bind is not None and not _has_column(bind, "document_pages", "extraction_status"):
        op.add_column(
            "document_pages",
            sa.Column("extraction_status", sa.String(24), nullable=True),
        )
    if bind is not None and not _has_column(bind, "document_pages", "question_count"):
        op.add_column(
            "document_pages",
            sa.Column("question_count", sa.Integer(), nullable=True),
        )
    if bind is not None and not _has_column(bind, "document_pages", "error_message"):
        op.add_column(
            "document_pages",
            sa.Column("error_message", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind is not None and _has_column(bind, "document_pages", "error_message"):
        op.drop_column("document_pages", "error_message")
    if bind is not None and _has_column(bind, "document_pages", "question_count"):
        op.drop_column("document_pages", "question_count")
    if bind is not None and _has_column(bind, "document_pages", "extraction_status"):
        op.drop_column("document_pages", "extraction_status")
