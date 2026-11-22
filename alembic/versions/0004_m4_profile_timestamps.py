# OfficerPath AI — PDF Engine (Phase 2, M4)
"""M4: add server defaults to student_profiles timestamps.

Revision ID: 0004_m4_profile_timestamps
Revises: 0003_m3_student_profiles
Create Date: 2026-11-22

Bug found by the M4 end-to-end run (not by the test suite): 0003
creates student_profiles.created_at / updated_at as NOT NULL with
NO server default, while the SQLAlchemy model declares
server_default=func.now() for both. The test suite never caught
it because conftest builds tables from the MODELS (which carry
the default); only a database built by `alembic upgrade head`
has the broken DDL — and on that database every profile insert
fails with `NOT NULL constraint failed:
student_profiles.created_at` (POST /api/v1/me 500).

This revision adds the missing defaults so the DDL matches the
model. Batch mode is used so the same revision works on SQLite
(which cannot ALTER a column default in place) and Postgres.
Downgrade only drops the defaults — no data is deleted, so no
row-count refusal is needed (unlike 0003's drop-table guard).
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004_m4_profile_timestamps"
down_revision = "0003_m3_student_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("student_profiles") as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("student_profiles") as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            server_default=None,
            existing_nullable=False,
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            server_default=None,
            existing_nullable=False,
        )
