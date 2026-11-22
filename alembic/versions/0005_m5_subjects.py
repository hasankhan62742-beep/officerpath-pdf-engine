# OfficerPath AI — PDF Engine (Phase 2, M5)
"""M5: subjects / topics / question_subjects (doc 03 §2.2).

Revision ID: 0005_m5_subjects
Revises: 0004_m4_profile_timestamps
Create Date: 2026-11-22

Creates the three tables from doc 03 §2.2 and seeds the 13
subjects from the Phase 2 prompt §12. No topics are seeded —
the topics table exists so M6+ can add them; in M5 the UI
assigns subjects only, by hand. Classification is optional:
a question with no row in question_subjects is simply
uncategorised, never force-categorised.

The seed is idempotent (ON CONFLICT DO NOTHING on Postgres,
INSERT OR IGNORE on SQLite) so re-running the revision never
duplicates a subject. Downgrade refuses while question_subjects
holds user assignments (doc 03 §6 — a downgrade never deletes
user data silently); the seed rows themselves are dropped with
the subjects table.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa

from alembic import op

revision = "0005_m5_subjects"
down_revision = "0004_m4_profile_timestamps"
branch_labels = None
depends_on = None

#: The 13 subjects from the Phase 2 prompt §12, in prompt order.
SUBJECTS: tuple[tuple[str, str], ...] = (
    ("General Knowledge", "general-knowledge"),
    ("Pakistan Affairs", "pakistan-affairs"),
    ("Current Affairs", "current-affairs"),
    ("Islamic Studies", "islamic-studies"),
    ("Everyday Science", "everyday-science"),
    ("English", "english"),
    ("Mathematics", "mathematics"),
    ("Computer Science", "computer-science"),
    ("Urdu", "urdu"),
    ("Geography", "geography"),
    ("History", "history"),
    ("Political Science", "political-science"),
    ("General Ability", "general-ability"),
)


def upgrade() -> None:
    op.create_table(
        "subjects",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("slug", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "topics",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("subject_id", sa.Uuid, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("slug", sa.Text, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subject_id", "slug", name="ix_topics_subject_slug"),
    )
    op.create_table(
        "question_subjects",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("question_id", sa.Uuid, nullable=False),
        sa.Column("subject_id", sa.Uuid, nullable=True),
        sa.Column("topic_id", sa.Uuid, nullable=True),
        sa.Column("assigned_by", sa.Uuid, nullable=False),
        sa.Column("confidence", sa.String(32), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["question_id"], ["extracted_questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "question_id", "subject_id", "topic_id", name="ix_question_subjects_qst"
        ),
    )
    op.create_index(
        "ix_question_subjects_subject", "question_subjects", ["subject_id", "created_at"]
    )
    # Idempotent seed: the same revision must be safe to re-run.
    # NOTE (M5 fix, found by E2E): insert the id as 32-char hex, NOT the
    # dashed str(uuid). The ORM maps Subject.id as sa.Uuid, which stores
    # CHAR(32) hex on SQLite; a dashed raw-SQL value never matches an
    # ORM filter (assign_subject 404'd "Subject not found" for a subject
    # the list endpoint returned). Postgres accepts undashed hex as a
    # uuid literal, so .hex is correct on both dialects.
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else "postgresql"
    for name, slug in SUBJECTS:
        if dialect == "sqlite":
            op.execute(
                sa.text(
                    "INSERT OR IGNORE INTO subjects (id, name, slug) VALUES (:id, :name, :slug)"
                ).bindparams(id=uuid.uuid4().hex, name=name, slug=slug)
            )
        else:
            op.execute(
                sa.text(
                    "INSERT INTO subjects (id, name, slug) VALUES (:id, :name, :slug) "
                    "ON CONFLICT (slug) DO NOTHING"
                ).bindparams(id=uuid.uuid4().hex, name=name, slug=slug)
            )


def downgrade() -> None:
    bind = op.get_bind()
    count = 0
    if bind is not None:
        count = int(bind.execute(sa.text("SELECT COUNT(*) FROM question_subjects")).scalar() or 0)
    if count > 0:
        raise RuntimeError(
            f"Refusing downgrade: question_subjects still holds {count} user "
            "assignment(s). Archive them first — a downgrade never deletes "
            "user data silently (doc 03 §6)."
        )
    op.drop_index("ix_question_subjects_subject", table_name="question_subjects")
    op.drop_table("question_subjects")
    op.drop_table("topics")
    op.drop_table("subjects")
