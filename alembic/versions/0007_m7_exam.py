# OfficerPath AI — PDF Engine (Phase 2, M7)
"""M7: exam interface tables — student_responses + test_results.

Revision ID: 0007_m7_exam
Revises: 0006_m6_tests
Create Date: 2026-11-22

Doc 03 §2.5, exactly, plus ONE recorded addition:
``test_results.unknown_count`` — doc 03's table has no unknown
count, but M7 must record unknown snapshots (correct_index -1)
separately: they are excluded from correct/incorrect/unattempted
AND from max_marks, never scored as wrong, never a 500. The
count lives on the result row so the M8 results UI can show
"1 question had no known answer and was not scored".

Template → session relationship (decided in M7, recorded here):
M6 already creates template + session 1:1 at build time — the
session IS the test instance. M7's start activates that same
session (created → in_progress, server_started_at from the
server clock). No new session row is created per attempt; a
retake is a new test (M8 handles retakes).

Downgrade: refuses while ``student_responses`` or
``test_results`` hold rows (doc 03 §6 — a downgrade never
deletes user data silently).
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0007_m7_exam"
down_revision = "0006_m6_tests"
branch_labels = None
depends_on = None

JSONVariant = sa.JSON().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "student_responses",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("session_id", sa.Uuid, nullable=False),
        sa.Column("snapshot_id", sa.Uuid, nullable=False),
        sa.Column("user_id", sa.Uuid, nullable=False),
        sa.Column("selected_index", sa.Integer, nullable=True),
        sa.Column("marked_for_review", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["session_id"], ["test_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["test_question_snapshots.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "snapshot_id", name="uq_response_session_snapshot"),
    )
    op.create_index(
        "ix_student_responses_session", "student_responses", ["session_id", "updated_at"]
    )
    op.create_index(
        "ix_student_responses_user_created", "student_responses", ["user_id", "updated_at"]
    )
    op.create_table(
        "test_results",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("session_id", sa.Uuid, nullable=False),
        sa.Column("user_id", sa.Uuid, nullable=False),
        sa.Column("total_questions", sa.Integer, nullable=False),
        sa.Column("correct_count", sa.Integer, nullable=False),
        sa.Column("incorrect_count", sa.Integer, nullable=False),
        sa.Column("unattempted_count", sa.Integer, nullable=False),
        sa.Column("unknown_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_marks", sa.Numeric(10, 2), nullable=False),
        sa.Column("max_marks", sa.Numeric(10, 2), nullable=False),
        sa.Column("percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("time_taken_seconds", sa.Integer, nullable=False),
        sa.Column("subject_breakdown", JSONVariant, nullable=True),
        sa.Column("topic_breakdown", JSONVariant, nullable=True),
        sa.Column("marking_config_id", sa.Uuid, nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["session_id"], ["test_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["marking_config_id"], ["marking_configs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_test_results_session"),
    )
    op.create_index("ix_test_results_user_created", "test_results", ["user_id", "created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    responses = 0
    results = 0
    if bind is not None:
        responses = int(
            bind.execute(sa.text("SELECT COUNT(*) FROM student_responses")).scalar() or 0
        )
        results = int(bind.execute(sa.text("SELECT COUNT(*) FROM test_results")).scalar() or 0)
    if responses > 0 or results > 0:
        raise RuntimeError(
            f"Refusing downgrade: student_responses holds {responses} row(s) and "
            f"test_results holds {results} row(s). Archive them first — "
            "a downgrade never deletes user data silently (doc 03 §6)."
        )
    op.drop_index("ix_test_results_user_created", table_name="test_results")
    op.drop_table("test_results")
    op.drop_index("ix_student_responses_user_created", table_name="student_responses")
    op.drop_index("ix_student_responses_session", table_name="student_responses")
    op.drop_table("student_responses")
