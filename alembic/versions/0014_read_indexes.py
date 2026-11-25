# OfficerPath AI — PDF Engine (B bugfix)
"""B: indexes the read paths were missing (bugs a/b).

Revision ID: 0014_read_indexes
Revises: 0013_a3_page_inventory
Create Date: 2026-11-26

Profiled 2026-11-26 on a realistic-volume local replica
(54,161 questions, 216,416 options, 54,104 answers):
EXPLAIN showed full table scans where every bank read filters
by question_id — ``SCAN question_options`` and ``SCAN
extracted_answers + USE TEMP B-TREE FOR ORDER BY`` — because
neither table had a question_id index (the ``_resolve_pool``
comment already admitted it). On the live 0.1-CPU free tier
those scans pushed the subject-wide bank list past the proxy
timeout ("Failed to fetch") and the section-counts call into
an endless spinner. The indexes:

- ``ix_question_options_question`` on
  ``question_options(question_id)`` — every ``_batch_options``
  call and the pool option-holder query.
- ``ix_extracted_answers_question_created`` on
  ``extracted_answers(question_id, created_at)`` — every
  ``_batch_answers`` / latest-answer query; the composite
  serves the filter and the latest-first order (read
  backwards), so no separate single-column index is needed.
- ``ix_question_subjects_topic`` on
  ``question_subjects(topic_id, question_id)`` — the
  counts-only availability query drives from topic_id, which
  the question-first index cannot serve.

Additive-only, touches no rows. Downgrade drops the three
indexes (reads get slow again, nothing else changes).

Guards (the 0013 precedent): the schema tests pre-create all
tables from the models before running ``upgrade head``, so a
blind create_index would fail with "already exists". Every
step checks first, making the revision safe on both paths —
migration-built tables and model-built tables.

LIVE APPLY: this Alembic revision covers fresh/local DBs built
by ``alembic upgrade head``. The live Supabase tables are
owned by migration 015, so the same indexes are added live by
supabase/migrations/023_read_indexes.sql (SQL Editor, owner
go-ahead) — the 019/020/021/022 precedent. The code in this
build works without the live indexes (it just stays slow) —
but the live slowness is only fixed once 023 is applied, so
apply 023 BEFORE deploying this build.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0014_read_indexes"
down_revision = "0013_a3_page_inventory"
branch_labels = None
depends_on = None

INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("question_options", "ix_question_options_question", ("question_id",)),
    (
        "extracted_answers",
        "ix_extracted_answers_question_created",
        ("question_id", "created_at"),
    ),
    ("question_subjects", "ix_question_subjects_topic", ("topic_id", "question_id")),
)


def _has_index(bind: object, table: str, name: str) -> bool:
    return name in {i["name"] for i in sa.inspect(bind).get_indexes(table)}  # type: ignore[arg-type]


def upgrade() -> None:
    bind = op.get_bind()
    for table, name, columns in INDEXES:
        if bind is not None and not _has_index(bind, table, name):
            op.create_index(name, table, list(columns))


def downgrade() -> None:
    bind = op.get_bind()
    for table, name, _columns in INDEXES:
        if bind is not None and _has_index(bind, table, name):
            op.drop_index(name, table_name=table)
