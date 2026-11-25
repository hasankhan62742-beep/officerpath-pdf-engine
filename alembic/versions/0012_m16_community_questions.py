# OfficerPath AI — PDF Engine (M16)
"""M16: community questions ("Add Questions").

Revision ID: 0012_m16_community_questions
Revises: 0011_m11_shared_bank
Create Date: 2026-11-25

A student submits a question + 4 options + correct answer +
explanation + subject + source; it waits as a staging row in
``community_questions`` until an admin approves it, and the
approval creates the real bank rows (ExtractedQuestion +
options + answer + subject assignment) under the shared
community document. Until approval the submission is invisible
to every pool.

- ``community_questions``: the staging table (status
  pending/approved/rejected, contributor id + display-name
  snapshot, ``paper`` = the paper the question appeared in as
  written by the contributor, fingerprint = SHA-256 of the
  normalized question text, the duplicate key within one
  subject).
- ``extracted_questions.contributor_name`` /
  ``community_question_id`` / ``paper``: attribution copied
  onto the bank row on approval, so reading mode can show
  "Submitted by ..." and "Paper: ...". NULL for every
  parsed/imported question.

Additive-only. Downgrade drops the two columns and the table.

Guards (the 0011 precedent): the schema tests pre-create all
tables from the models before running ``upgrade head``, so a
blind create_table / add_column would fail with "already
exists". Every step checks first, making the revision safe on
both paths — migration-built tables and model-built tables.

LIVE APPLY: this Alembic revision covers fresh/local DBs
built by ``alembic upgrade head``. The live Supabase tables
are owned by migration 015, so the same objects are added
live by supabase/migrations/021_community_questions.sql (SQL
Editor, owner go-ahead) — the 019/020 precedent.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0012_m16_community_questions"
down_revision = "0011_m11_shared_bank"
branch_labels = None
depends_on = None


def _has_table(bind: object, table: str) -> bool:
    return sa.inspect(bind).has_table(table)  # type: ignore[arg-type]


def _has_column(bind: object, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}  # type: ignore[arg-type]


def upgrade() -> None:
    bind = op.get_bind()
    if bind is not None and not _has_table(bind, "community_questions"):
        op.create_table(
            "community_questions",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("contributor_id", sa.Uuid(), nullable=False),
            sa.Column("contributor_name", sa.Text(), nullable=False),
            sa.Column("question_text", sa.Text(), nullable=False),
            sa.Column("options", sa.JSON(), nullable=False),
            sa.Column("correct_index", sa.Integer(), nullable=False),
            sa.Column("explanation", sa.Text(), nullable=True),
            sa.Column("subject_id", sa.Uuid(), nullable=True),
            sa.Column("topic_id", sa.Uuid(), nullable=True),
            sa.Column("source", sa.Text(), nullable=True),
            sa.Column("paper", sa.Text(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
            sa.Column("review_note", sa.Text(), nullable=True),
            sa.Column("reviewed_by", sa.Uuid(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("bank_question_id", sa.Uuid(), nullable=True),
            sa.Column("fingerprint", sa.String(64), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.CheckConstraint(
                "status IN ('pending', 'approved', 'rejected')",
                name="ck_community_questions_status",
            ),
            sa.CheckConstraint(
                "correct_index >= 0 AND correct_index <= 3",
                name="ck_community_questions_correct_index",
            ),
            sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(
                ["bank_question_id"], ["extracted_questions.id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_community_questions_contributor_created",
            "community_questions",
            ["contributor_id", "created_at"],
        )
        op.create_index(
            "ix_community_questions_status_created",
            "community_questions",
            ["status", "created_at"],
        )
        op.create_index(
            "ix_community_questions_fingerprint",
            "community_questions",
            ["fingerprint"],
        )
    if bind is not None and not _has_column(bind, "extracted_questions", "contributor_name"):
        op.add_column(
            "extracted_questions",
            sa.Column("contributor_name", sa.Text(), nullable=True),
        )
    if bind is not None and not _has_column(bind, "extracted_questions", "community_question_id"):
        op.add_column(
            "extracted_questions",
            sa.Column("community_question_id", sa.Uuid(), nullable=True),
        )
    if bind is not None and not _has_column(bind, "extracted_questions", "paper"):
        op.add_column(
            "extracted_questions",
            sa.Column("paper", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind is not None and _has_column(bind, "extracted_questions", "paper"):
        op.drop_column("extracted_questions", "paper")
    if bind is not None and _has_column(bind, "extracted_questions", "community_question_id"):
        op.drop_column("extracted_questions", "community_question_id")
    if bind is not None and _has_column(bind, "extracted_questions", "contributor_name"):
        op.drop_column("extracted_questions", "contributor_name")
    if bind is not None and _has_table(bind, "community_questions"):
        op.drop_table("community_questions")
