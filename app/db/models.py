# OfficerPath AI — PDF Engine (Phase 1, M1)
# SQLAlchemy 2.x models for the prompt §14 schema.
#
# Ownership split (ADR-003):
# - `documents` + `jobs` are created by Supabase migration 015
#   (supabase/migrations/015_documents_jobs.sql). The models below
#   MIRROR those two tables (read/write through SQLAlchemy where the
#   engine needs joins) but Alembic revision 0001 does NOT create them.
# - Every other table here IS created by Alembic 0001. Its foreign keys
#   reference documents.id / jobs.id, so apply 015 BEFORE Alembic 0001.
# - Original content and normalized content are stored separately
#   (original_text vs normalized_text) per prompt §14. Nothing derived
#   ever overwrites an original.
# - All ids are UUIDs; timestamps are timezone-aware; audit tables are
#   append-only (no update/delete methods exist for them by design).
# - JSON columns use JSONB on Postgres, plain JSON on SQLite (tests).

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JSONVariant = JSONB().with_variant(JSON(), "sqlite")


class Base(DeclarativeBase):
    """Shared base. No table is created from Base itself."""

    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _updated_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


# ---------------------------------------------------------------------------
# Tables owned by Supabase migration 015 (mirrored here, NOT Alembic-managed)
# ---------------------------------------------------------------------------


class Document(Base):
    """One uploaded document (metadata only; the file lives in storage).

    Mirrors public.documents from migration 015. content_hash is added
    by the revised 015 (M1) and is the SHA-256 dedup key (per user).
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONVariant, nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()

    pages: Mapped[list[DocumentPage]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    stages: Mapped[list[ProcessingStage]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_documents_user_created", "user_id", "created_at"),
        Index("ix_documents_user_hash", "user_id", "content_hash"),
    )


class Job(Base):
    """One durable processing job per document. Mirrors public.jobs (015)."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    created_at: Mapped[datetime] = _created_at()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_jobs_user_created", "user_id", "created_at"),
        Index("ix_jobs_active", "status"),
    )


# ---------------------------------------------------------------------------
# Tables created by Alembic 0001 (engine-owned §14 schema)
# ---------------------------------------------------------------------------


class DocumentPage(Base):
    """One page of a document, with its classification + quality metrics.

    Page classification is per page, never per document (prompt §6):
    digital / scanned / mixed / blank / unreadable / unknown. Quality
    metrics that M1 cannot measure (skew, blur, noise — need OpenCV in
    M2) are NULL with measurement_method recorded, never invented.
    """

    __tablename__ = "document_pages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    classification: Mapped[str] = mapped_column(String(16), nullable=False)
    classification_method: Mapped[str] = mapped_column(String(32), nullable=False)
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    width_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dpi_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    rotation_degrees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skew_degrees: Mapped[float | None] = mapped_column(Float, nullable=True)
    blur_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    noise_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    contrast_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    has_text_layer: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    original_render_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_render_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    preprocessing_applied: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    # M3: layout analysis result for the page (columns, regions,
    # tables, figures, continuation flags) — Alembic 0002.
    layout_applied: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    created_at: Mapped[datetime] = _created_at()

    document: Mapped[Document] = relationship(back_populates="pages")

    __table_args__ = (
        Index(
            "ix_document_pages_doc_page",
            "document_id",
            "page_number",
            unique=True,
        ),
    )


class ProcessingStage(Base):
    """One persisted pipeline-stage transition for a document.

    Implements the prompt §5.3 state machine history: every stage
    transition is a row (append-only). Stage names:
    uploaded, validated, queued, preprocessing, ocr_done, layout_done,
    extracted, answers_detected, matched, scored, completed,
    requires_review, failed. Transitions are validated by the service
    layer (M6+); this table only records them.
    """

    __tablename__ = "processing_stages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()

    document: Mapped[Document] = relationship(back_populates="stages")

    __table_args__ = (Index("ix_processing_stages_doc", "document_id", "created_at"),)


class OCRBlock(Base):
    """One normalized OCR output block (prompt §8).

    Stores the ORIGINAL engine output verbatim (text + boxes +
    confidences + engine name/version). Corrections are layered in
    later tables; this row is never edited after insert.
    """

    __tablename__ = "ocr_blocks"

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    page_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    engine: Mapped[str] = mapped_column(String(32), nullable=False)
    engine_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    bbox_x_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_y_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_x_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_y_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    reading_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    word_confidences: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    style: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (Index("ix_ocr_blocks_doc_page", "document_id", "page_number"),)


class ExtractedQuestion(Base):
    """One extracted MCQ. Original and normalized text kept apart."""

    __tablename__ = "extracted_questions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    question_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_pages: Mapped[list[int] | None] = mapped_column(JSONVariant, nullable=True)
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    extraction_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rule_set_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unreviewed")
    content_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("extracted_questions.id", ondelete="SET NULL"),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    options: Mapped[list[QuestionOption]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )
    answers: Mapped[list[ExtractedAnswer]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_questions_doc", "document_id", "created_at"),
        Index("ix_questions_fingerprint", "content_fingerprint"),
    )


class QuestionOption(Base):
    """One option of an extracted question."""

    __tablename__ = "question_options"

    id: Mapped[uuid.UUID] = _uuid_pk()
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("extracted_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    original_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    normalized_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    label_inferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = _created_at()

    question: Mapped[ExtractedQuestion] = relationship(back_populates="options")


class QuestionAsset(Base):
    """A figure/diagram cropped from a page and linked to a question."""

    __tablename__ = "question_assets"

    id: Mapped[uuid.UUID] = _uuid_pk()
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("extracted_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = _created_at()


class ExtractedAnswer(Base):
    """The resolved answer state for one question.

    The answer itself is a claim; the supporting records live in
    answer_evidence. status values (prompt §11.2):
    verified_explicit_key, detected_inline, detected_visual,
    detected_digital_style, inferred_formatting, conflicting,
    unmatched, missing, manually_verified.
    """

    __tablename__ = "extracted_answers"

    id: Mapped[uuid.UUID] = _uuid_pk()
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("extracted_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    resolved_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    resolution_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolution_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    question: Mapped[ExtractedQuestion] = relationship(back_populates="answers")
    evidence: Mapped[list[AnswerEvidence]] = relationship(
        back_populates="answer", cascade="all, delete-orphan"
    )


class AnswerEvidence(Base):
    """One evidence record supporting (or contesting) an answer.

    Append-only: evidence is never edited; a correction adds a new
    record and the answer is re-resolved (M6).
    """

    __tablename__ = "answer_evidence"

    id: Mapped[uuid.UUID] = _uuid_pk()
    answer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("extracted_answers.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("answer_sources.id", ondelete="SET NULL"), nullable=True
    )
    value_original: Mapped[str | None] = mapped_column(String(64), nullable=True)
    value_normalized: Mapped[str | None] = mapped_column(String(16), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    detector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detector_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    artifact_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created_at()

    answer: Mapped[ExtractedAnswer] = relationship(back_populates="evidence")


class AnswerSource(Base):
    """A detected answer source: a key table, an inline answer, a visual
    marking region, a handwriting region. One source can feed many
    evidence records (e.g. one key table → 100 answers)."""

    __tablename__ = "answer_sources"

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    page_numbers: Mapped[list[int] | None] = mapped_column(JSONVariant, nullable=True)
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    detector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detector_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = _created_at()


class ExtractionReport(Base):
    """The explainable per-document extraction report (prompt §13)."""

    __tablename__ = "extraction_reports"

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    rule_set_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pages_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    questions_extracted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    questions_missing_options: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uncertain_answers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conflicting_answers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unmatched_key_entries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicates_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    engine_disagreements: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requires_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_reasons: Mapped[list[str] | None] = mapped_column(JSONVariant, nullable=True)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (Index("ix_reports_doc", "document_id", "created_at"),)


class ManualCorrection(Base):
    """A human correction layered on top of extracted content.

    Corrections never edit the original rows: they reference the target
    row + field, store old/new values, and are audited (M6 review APIs).
    """

    __tablename__ = "manual_corrections"

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (Index("ix_corrections_doc", "document_id", "created_at"),)


class ReviewHistory(Base):
    """Append-only record of review decisions (accept / flag / verify)."""

    __tablename__ = "review_history"

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created_at()


class ProcessingError(Base):
    """One recorded processing failure (error taxonomy code + context).

    A failed page never fails the whole document silently (prompt §2):
    page-level failures are rows here, linked to the document + stage.
    """

    __tablename__ = "processing_errors"

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_code: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (Index("ix_errors_doc", "document_id", "created_at"),)


class AuditLog(Base):
    """Append-only audit trail (who did what to whose document, when).

    No update/delete API exists for this table anywhere in the codebase.
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (Index("ix_audit_doc", "document_id", "created_at"),)


class RuleSetVersion(Base):
    """A versioned detector/extraction rule set (YAML/JSON in storage).

    Detectors are configured by versioned rule sets, not hardcoded
    constants (prompt §5.2). Rows here record which version produced
    which extraction (extracted_questions.rule_set_version).
    """

    __tablename__ = "rule_set_versions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    rules: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (Index("ix_rulesets_name_version", "name", "version", unique=True),)
