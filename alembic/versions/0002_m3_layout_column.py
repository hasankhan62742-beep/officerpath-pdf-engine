# OfficerPath AI — PDF Engine (Phase 1, M3)
"""M3: add layout_applied JSON to document_pages.

Revision ID: 0002_m3_layout_column
Revises: 0001_m1_engine_tables
Create Date: 2026-11-21

Additive-only, nullable column: existing rows are unaffected.
Downgrade drops the column. The column holds the per-page layout
analysis result (columns, regions, tables, figures, continuation
flags) produced by the M3 layout stage.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0002_m3_layout_column"
down_revision = "0001_m1_engine_tables"
branch_labels = None
depends_on = None

JSONVariant = JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.add_column("document_pages", sa.Column("layout_applied", JSONVariant, nullable=True))


def downgrade() -> None:
    op.drop_column("document_pages", "layout_applied")
