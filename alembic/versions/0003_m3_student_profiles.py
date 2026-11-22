# OfficerPath AI — PDF Engine (Phase 2, M3)
"""M3: create student_profiles (doc 03 §2.1).

Revision ID: 0003_m3_student_profiles
Revises: 0002_m3_layout_column
Create Date: 2026-11-22

One profile per Supabase Auth user (web student). Lives in the
ENGINE DB, not in Supabase migrations — the engine owns it. Do NOT
confuse it with the Flutter app's Supabase `profiles` table (plan /
premium / admin), which the engine never writes.

Downgrade refuses when rows exist (doc 03 §6): dropping a table
that holds user data silently is forbidden — archive first, then
downgrade.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003_m3_student_profiles"
down_revision = "0002_m3_layout_column"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("preferred_exam", sa.Text(), nullable=True),
        sa.Column("education_level", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        "ix_student_profiles_user_created",
        "student_profiles",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    count = bind.execute(sa.text("SELECT COUNT(*) FROM student_profiles")).scalar()
    if count:
        raise RuntimeError(
            f"Refusing to drop student_profiles: it holds {count} row(s). "
            "Archive the profiles first, then downgrade."
        )
    op.drop_index("ix_student_profiles_user_created", table_name="student_profiles")
    op.drop_table("student_profiles")
