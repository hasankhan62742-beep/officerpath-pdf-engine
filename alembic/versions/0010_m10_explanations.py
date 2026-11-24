# OfficerPath AI — PDF Engine (Phase 2, M10)
"""M10: stored explanations — explanation columns on the bank and on snapshots.

Revision ID: 0010_m10_explanations
Revises: 0009_m9_notifications
Create Date: 2026-11-24

Owner rule: after a test, every wrong answer shows its
explanation in the SAME question card (results review +
mistake notebook). Until now no explanation was stored
anywhere — the result page said so explicitly ("No
explanations are shown because none were stored").

- ``extracted_questions.explanation``: verbatim explanation /
  solution as stored by the source, written by the
  question-bank import. NULL = the source gave none
  (solution_missing); an explanation is NEVER invented.
- ``test_question_snapshots.explanation``: frozen copy taken
  at test creation, so a past test keeps the explanation it
  was taken with even if the bank question is later edited.

Additive-only, nullable columns: existing rows are
unaffected. Downgrade drops the columns (the 0002
precedent for a derived-content column — the stored text
is source content, not user-authored data).
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0010_m10_explanations"
down_revision = "0009_m9_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("extracted_questions", sa.Column("explanation", sa.Text(), nullable=True))
    op.add_column("test_question_snapshots", sa.Column("explanation", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("test_question_snapshots", "explanation")
    op.drop_column("extracted_questions", "explanation")
