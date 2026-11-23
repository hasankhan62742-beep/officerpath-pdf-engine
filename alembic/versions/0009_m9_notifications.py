# OfficerPath AI — PDF Engine (Phase 2, M9)
"""M9: admin foundation + notifications — notifications table.

Revision ID: 0009_m9_notifications
Revises: 0008_m8_collections
Create Date: 2026-11-23

Doc 03 §2.6, exactly: in-app notifications only (no email is
ever claimed sent). Columns: id, user_id (NOT NULL — M9 decides
per-user only, no broadcast NULL in Phase 2), type CHECK over
the six doc-03 types, title/body NOT NULL, link NULL (in-app
route), is_read default false, created_at.

DOC DRIFT NOTE: the M9 scope line in
docs/phase2/07-milestone-execution-plan.md says "Alembic 0006"
for notifications — that is STALE. 0006 was taken by M6
(test templates/sessions/snapshots), 0007 by M7 (exam),
0008 by M8 (collections). 0009 is the next sequential
revision; the plan line should read 0009.

Downgrade: refuses while ``notifications`` holds rows
(doc 03 §6 — a downgrade never deletes user data silently).
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009_m9_notifications"
down_revision = "0008_m8_collections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("user_id", sa.Uuid, nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("link", sa.String(500), nullable=True),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "type IN ('upload_done', 'upload_failed', 'review_needed', "
            "'test_submitted', 'result_ready', 'subscription_change')",
            name="ck_notification_type",
        ),
    )
    op.create_index(
        "ix_notifications_user_created",
        "notifications",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_notifications_user_unread",
        "notifications",
        ["user_id", "is_read", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    count = 0
    if bind is not None:
        count = int(bind.execute(sa.text("SELECT COUNT(*) FROM notifications")).scalar() or 0)
    if count > 0:
        raise RuntimeError(
            f"Refusing downgrade: notifications holds {count} row(s). "
            "Archive them first — a downgrade never deletes user data silently (doc 03 §6)."
        )
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_table("notifications")
