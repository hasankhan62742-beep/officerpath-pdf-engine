# OfficerPath AI — PDF Engine (Phase 2, M8)
"""M8: results + analytics collections — student_question_collections.

Revision ID: 0008_m8_collections
Revises: 0007_m7_exam
Create Date: 2026-11-22

Doc 03 §2.3, exactly: one table for bookmarks + the mistake
notebook + custom collections, distinguished by
``collection_type`` (CHECK: bookmark / mistake / custom) and
UNIQUE(user_id, question_id, collection_type) — a student
bookmarks a question once, and the submit flow never writes a
duplicate mistake row for the same question.

Downgrade: refuses while ``student_question_collections`` holds
rows (doc 03 §6 — a downgrade never deletes user data silently).
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008_m8_collections"
down_revision = "0007_m7_exam"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_question_collections",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("user_id", sa.Uuid, nullable=False),
        sa.Column("question_id", sa.Uuid, nullable=False),
        sa.Column("collection_type", sa.String(32), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["question_id"], ["extracted_questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "question_id",
            "collection_type",
            name="uq_collection_user_question_type",
        ),
        sa.CheckConstraint(
            "collection_type IN ('bookmark', 'mistake', 'custom')",
            name="ck_collection_type",
        ),
    )
    op.create_index(
        "ix_collections_user_type_created",
        "student_question_collections",
        ["user_id", "collection_type", "created_at"],
    )
    op.create_index(
        "ix_collections_question", "student_question_collections", ["question_id", "created_at"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    count = 0
    if bind is not None:
        count = int(
            bind.execute(sa.text("SELECT COUNT(*) FROM student_question_collections")).scalar() or 0
        )
    if count > 0:
        raise RuntimeError(
            f"Refusing downgrade: student_question_collections holds {count} row(s). "
            "Archive them first — a downgrade never deletes user data silently (doc 03 §6)."
        )
    op.drop_index("ix_collections_question", table_name="student_question_collections")
    op.drop_index("ix_collections_user_type_created", table_name="student_question_collections")
    op.drop_table("student_question_collections")
