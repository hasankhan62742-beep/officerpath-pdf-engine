# OfficerPath AI — PDF Engine (Phase 1, M1)
"""M1: create the engine-owned §14 tables.

Revision ID: 0001_m1_engine_tables
Revises: (none — first Alembic revision)
Create Date: 2026-11-21

PREREQUISITE: Supabase migration 015 must already be applied
(documents + jobs tables exist), because the tables below carry
foreign keys to documents.id / jobs.id. Apply order:
  1. Dashboard SQL Editor: supabase/migrations/015_documents_jobs.sql
  2. Alembic: DATABASE_URL=... alembic upgrade head

This revision creates ONLY the new engine-owned tables. It does NOT
create documents/jobs (015 owns them) and does NOT modify any
pre-existing table. Downgrade drops exactly the tables created here.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0001_m1_engine_tables"
down_revision = None
branch_labels = None
depends_on = None

JSONVariant = JSONB().with_variant(sa.JSON(), "sqlite")


def _id_column() -> sa.Column:
    return sa.Column("id", sa.Uuid, primary_key=True)


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


def _updated_at() -> sa.Column:
    return sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


def upgrade() -> None:
    op.create_table(
        "document_pages",
        _id_column(),
        sa.Column(
            "document_id",
            sa.Uuid,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer, nullable=False),
        sa.Column("classification", sa.String(16), nullable=False),
        sa.Column("classification_method", sa.String(32), nullable=False),
        sa.Column("classification_confidence", sa.Float, nullable=True),
        sa.Column("width_px", sa.Integer, nullable=True),
        sa.Column("height_px", sa.Integer, nullable=True),
        sa.Column("dpi_estimate", sa.Float, nullable=True),
        sa.Column("rotation_degrees", sa.Integer, nullable=True),
        sa.Column("skew_degrees", sa.Float, nullable=True),
        sa.Column("blur_score", sa.Float, nullable=True),
        sa.Column("noise_score", sa.Float, nullable=True),
        sa.Column("contrast_score", sa.Float, nullable=True),
        sa.Column("has_text_layer", sa.Boolean, nullable=True),
        sa.Column("original_render_path", sa.Text, nullable=True),
        sa.Column("processed_render_path", sa.Text, nullable=True),
        sa.Column("preprocessing_applied", JSONVariant, nullable=True),
        _created_at(),
        sa.UniqueConstraint("document_id", "page_number", name="uq_document_pages_doc_page"),
    )

    op.create_table(
        "processing_stages",
        _id_column(),
        sa.Column(
            "document_id",
            sa.Uuid,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_id", sa.Uuid, sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("page_number", sa.Integer, nullable=True),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("detail", JSONVariant, nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
    )
    op.create_index("ix_processing_stages_doc", "processing_stages", ["document_id", "created_at"])

    op.create_table(
        "ocr_blocks",
        _id_column(),
        sa.Column(
            "document_id",
            sa.Uuid,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "page_id",
            sa.Uuid,
            sa.ForeignKey("document_pages.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("page_number", sa.Integer, nullable=False),
        sa.Column("engine", sa.String(32), nullable=False),
        sa.Column("engine_version", sa.String(32), nullable=True),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("bbox_x_min", sa.Float, nullable=True),
        sa.Column("bbox_y_min", sa.Float, nullable=True),
        sa.Column("bbox_x_max", sa.Float, nullable=True),
        sa.Column("bbox_y_max", sa.Float, nullable=True),
        sa.Column("reading_order", sa.Integer, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("word_confidences", JSONVariant, nullable=True),
        sa.Column("style", JSONVariant, nullable=True),
        _created_at(),
    )
    op.create_index("ix_ocr_blocks_doc_page", "ocr_blocks", ["document_id", "page_number"])

    op.create_table(
        "extracted_questions",
        _id_column(),
        sa.Column(
            "document_id",
            sa.Uuid,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_id", sa.Uuid, sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("question_number", sa.String(32), nullable=True),
        sa.Column("original_text", sa.Text, nullable=False),
        sa.Column("normalized_text", sa.Text, nullable=False),
        sa.Column("source_pages", JSONVariant, nullable=True),
        sa.Column("bbox", JSONVariant, nullable=True),
        sa.Column("extraction_method", sa.String(64), nullable=True),
        sa.Column("rule_set_version", sa.String(32), nullable=True),
        sa.Column("ocr_confidence", sa.Float, nullable=True),
        sa.Column("extraction_confidence", sa.Float, nullable=True),
        sa.Column("validation_status", sa.String(32), nullable=False, server_default="unreviewed"),
        sa.Column("content_fingerprint", sa.String(64), nullable=True),
        sa.Column(
            "duplicate_of_id",
            sa.Uuid,
            sa.ForeignKey("extracted_questions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
    )
    op.create_index("ix_questions_doc", "extracted_questions", ["document_id", "created_at"])
    op.create_index("ix_questions_fingerprint", "extracted_questions", ["content_fingerprint"])

    op.create_table(
        "question_options",
        _id_column(),
        sa.Column(
            "question_id",
            sa.Uuid,
            sa.ForeignKey("extracted_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_label", sa.String(16), nullable=True),
        sa.Column("normalized_label", sa.String(16), nullable=True),
        sa.Column("label_inferred", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("original_text", sa.Text, nullable=False),
        sa.Column("normalized_text", sa.Text, nullable=False),
        sa.Column("bbox", JSONVariant, nullable=True),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        _created_at(),
    )

    op.create_table(
        "question_assets",
        _id_column(),
        sa.Column(
            "question_id",
            sa.Uuid,
            sa.ForeignKey("extracted_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.Uuid,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("storage_path", sa.Text, nullable=False),
        sa.Column("bbox", JSONVariant, nullable=True),
        sa.Column("page_number", sa.Integer, nullable=True),
        _created_at(),
    )

    op.create_table(
        "extracted_answers",
        _id_column(),
        sa.Column(
            "question_id",
            sa.Uuid,
            sa.ForeignKey("extracted_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.Uuid,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("resolved_label", sa.String(16), nullable=True),
        sa.Column("resolution_method", sa.String(64), nullable=True),
        sa.Column("resolution_score", sa.Float, nullable=True),
        _created_at(),
        _updated_at(),
    )

    op.create_table(
        "answer_sources",
        _id_column(),
        sa.Column(
            "document_id",
            sa.Uuid,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(256), nullable=True),
        sa.Column("page_numbers", JSONVariant, nullable=True),
        sa.Column("bbox", JSONVariant, nullable=True),
        sa.Column("raw_text", sa.Text, nullable=True),
        sa.Column("detector", sa.String(64), nullable=True),
        sa.Column("detector_confidence", sa.Float, nullable=True),
        _created_at(),
    )

    op.create_table(
        "answer_evidence",
        _id_column(),
        sa.Column(
            "answer_id",
            sa.Uuid,
            sa.ForeignKey("extracted_answers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column(
            "source_id",
            sa.Uuid,
            sa.ForeignKey("answer_sources.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("value_original", sa.String(64), nullable=True),
        sa.Column("value_normalized", sa.String(16), nullable=True),
        sa.Column("page_number", sa.Integer, nullable=True),
        sa.Column("bbox", JSONVariant, nullable=True),
        sa.Column("detector", sa.String(64), nullable=True),
        sa.Column("detector_confidence", sa.Float, nullable=True),
        sa.Column("artifact_ref", sa.Text, nullable=True),
        _created_at(),
    )

    op.create_table(
        "extraction_reports",
        _id_column(),
        sa.Column(
            "document_id",
            sa.Uuid,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_id", sa.Uuid, sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rule_set_version", sa.String(32), nullable=True),
        sa.Column("pages_processed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pages_failed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("questions_extracted", sa.Integer, nullable=False, server_default="0"),
        sa.Column("questions_missing_options", sa.Integer, nullable=False, server_default="0"),
        sa.Column("uncertain_answers", sa.Integer, nullable=False, server_default="0"),
        sa.Column("conflicting_answers", sa.Integer, nullable=False, server_default="0"),
        sa.Column("unmatched_key_entries", sa.Integer, nullable=False, server_default="0"),
        sa.Column("duplicates_found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("engine_disagreements", sa.Integer, nullable=False, server_default="0"),
        sa.Column("requires_review", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("review_reasons", JSONVariant, nullable=True),
        sa.Column("summary", JSONVariant, nullable=True),
        _created_at(),
    )
    op.create_index("ix_reports_doc", "extraction_reports", ["document_id", "created_at"])

    op.create_table(
        "manual_corrections",
        _id_column(),
        sa.Column(
            "document_id",
            sa.Uuid,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid, nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("field_name", sa.String(64), nullable=False),
        sa.Column("target_id", sa.Uuid, nullable=False),
        sa.Column("old_value", sa.Text, nullable=True),
        sa.Column("new_value", sa.Text, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        _created_at(),
    )
    op.create_index("ix_corrections_doc", "manual_corrections", ["document_id", "created_at"])

    op.create_table(
        "review_history",
        _id_column(),
        sa.Column(
            "document_id",
            sa.Uuid,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reviewer_id", sa.Uuid, nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.Uuid, nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        _created_at(),
    )

    op.create_table(
        "processing_errors",
        _id_column(),
        sa.Column(
            "document_id",
            sa.Uuid,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_id", sa.Uuid, sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("page_number", sa.Integer, nullable=True),
        sa.Column("stage", sa.String(32), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("detail", JSONVariant, nullable=True),
        _created_at(),
    )
    op.create_index("ix_errors_doc", "processing_errors", ["document_id", "created_at"])

    op.create_table(
        "audit_log",
        _id_column(),
        sa.Column("user_id", sa.Uuid, nullable=True),
        sa.Column(
            "document_id",
            sa.Uuid,
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=True),
        sa.Column("target_id", sa.Uuid, nullable=True),
        sa.Column("detail", JSONVariant, nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        _created_at(),
    )
    op.create_index("ix_audit_doc", "audit_log", ["document_id", "created_at"])

    op.create_table(
        "rule_set_versions",
        _id_column(),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("rules", JSONVariant, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.false()),
        _created_at(),
        sa.UniqueConstraint("name", "version", name="uq_rulesets_name_version"),
    )


def downgrade() -> None:
    for table in (
        "rule_set_versions",
        "audit_log",
        "processing_errors",
        "review_history",
        "manual_corrections",
        "extraction_reports",
        "answer_evidence",
        "answer_sources",
        "extracted_answers",
        "question_assets",
        "question_options",
        "extracted_questions",
        "ocr_blocks",
        "processing_stages",
        "document_pages",
    ):
        op.drop_table(table)
