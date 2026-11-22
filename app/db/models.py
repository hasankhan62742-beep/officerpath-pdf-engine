# OfficerPath AI — PDF Engine (Phase 1, M1)
# SQLAlchemy 2.x models for the prompt §14 schema.
#
# Ownership split (ADR-003, ADR-011):
# - `documents` + `jobs` are created by Supabase migration 015
#   (supabase/migrations/015_documents_jobs.sql). The models below
#   MIRROR those two tables (read/write through SQLAlchemy where the
#   engine needs joins) but Alembic revision 0001 does NOT create them.
#   Since ADR-011 (Phase 2 M3) the engine is the SINGLE access path
#   for both tables — the PostgREST repositories are deleted; the
#   Supabase tables stay live and untouched, and the same Postgres
#   database is used through DATABASE_URL.
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
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
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
        # M6: partial UNIQUE index — the dedup rule (same user +
        # same SHA-256 -> same document) applies only to LIVE rows.
        # The plain unique index in 015 made delete-then-re-upload
        # of the same file fail with a 500 (UNIQUE constraint
        # failed: documents.user_id, documents.content_hash),
        # because the soft-deleted row still held the unique slot
        # while the dedup lookup correctly ignored it (M4). A
        # deleted row must never block a fresh upload of the same
        # file. Mirrored by Alembic 0006 and Supabase migration 017
        # (live 015 still has the plain index until 017 is applied).
        Index(
            "ix_documents_user_hash",
            "user_id",
            "content_hash",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
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
# Tables created by Alembic 0003 (Phase 2, M3 — student profiles)
# ---------------------------------------------------------------------------


class StudentProfile(Base):
    """One profile per Supabase Auth user (web student).

    Lives in the ENGINE DB (doc 03 §2.1), not in Supabase
    migrations: the engine owns it and migrates it with Alembic.
    Do NOT confuse it with the Flutter app's Supabase `profiles`
    table (plan/premium/admin — the engine never writes those).

    `user_id` is the Supabase Auth user id. A foreign key to
    auth.users is NOT enforceable from the engine DB (different
    connection path); uniqueness + ownership are enforced in code
    (`app/services/profiles.py` — one row per user, JWT user id
    only, never a client-supplied user_id)."""

    __tablename__ = "student_profiles"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_exam: Mapped[str | None] = mapped_column(Text, nullable=True)
    education_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __table_args__ = (Index("ix_student_profiles_user_created", "user_id", "created_at"),)


# ---------------------------------------------------------------------------
# Tables created by Alembic 0005 (Phase 2, M5 — subjects / topics)
# ---------------------------------------------------------------------------


class Subject(Base):
    """A global reference subject (doc 03 §2.2).

    Seeded with the 13 subjects from the Phase 2 prompt §12.
    Global, not per-user; a question with no row in
    ``question_subjects`` is simply uncategorised — the UI must
    never force a category. Classification is optional and, in
    M5, manual only: the engine does NOT auto-classify."""

    __tablename__ = "subjects"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class Topic(Base):
    """A topic inside one subject (doc 03 §2.2). No topics are
    seeded in M5 — the table exists so M6+ can add them; the UI
    assigns subjects only until topics exist."""

    __tablename__ = "topics"

    id: Mapped[uuid.UUID] = _uuid_pk()
    subject_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __table_args__ = (Index("ix_topics_subject_slug", "subject_id", "slug", unique=True),)


class QuestionSubject(Base):
    """A manual subject/topic assignment for one extracted
    question (doc 03 §2.2). ``assigned_by`` is the user who
    assigned it; ``confidence`` is ``manual`` (M5 assigns by hand
    only) or ``unassigned``. One row per (question, subject,
    topic) — a question may carry several subjects."""

    __tablename__ = "question_subjects"

    id: Mapped[uuid.UUID] = _uuid_pk()
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("extracted_questions.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True
    )
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("topics.id", ondelete="SET NULL"), nullable=True
    )
    assigned_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    confidence: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __table_args__ = (
        Index(
            "ix_question_subjects_qst",
            "question_id",
            "subject_id",
            "topic_id",
            unique=True,
        ),
        Index("ix_question_subjects_subject", "subject_id", "created_at"),
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


# ---------------------------------------------------------------------------
# Tables created by Alembic 0006 (Phase 2, M6 — test builder)
# ---------------------------------------------------------------------------


class MarkingConfig(Base):
    """One marking scheme (doc 03 §2.4).

    Seeded with the PPSC default (+1 / −0.25 / 0). A test stores
    its marking_config_id, so the scheme travels with the test
    session and survives later edits. Custom configs are created
    by the test builder (validated ranges — see
    app/services/tests.py); marking is always computed on the
    backend (M7/M8), never trusted from the frontend.
    """

    __tablename__ = "marking_configs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    correct_marks: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    incorrect_marks: Mapped[float] = mapped_column(Float, nullable=False, default=-0.25)
    unattempted_marks: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class TestTemplate(Base):
    """One saved test definition (doc 03 §2.4).

    The template records HOW the test was built (source, count,
    repetition/unknown flags, selection seed, marking config) so
    the build is reproducible and auditable. The frozen content
    lives in the session's snapshots, not here.
    """

    __tablename__ = "test_templates"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ids: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    allow_repetition: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    include_unknown: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    selection_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Creation-time exclusion counts (how many bank questions were
    # left out of the pool and why) — stored so the test view can
    # explain its own selection honestly, forever.
    excluded_unknown: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    excluded_no_options: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    marking_config_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("marking_configs.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __table_args__ = (Index("ix_test_templates_user_created", "user_id", "created_at"),)


class TestSession(Base):
    """One concrete test instance (doc 03 §2.4).

    A test IS a session in M6: creating a test creates a
    template + a session in status ``created`` in one transaction,
    plus its frozen snapshots. Taking the test (M7) moves the
    status to ``in_progress`` and populates ``server_started_at``
    (nullable in M6 — no exam has started yet; M7 sets it at
    start, never from the browser clock).
    """

    __tablename__ = "test_sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("test_templates.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    marking_config_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("marking_configs.id", ondelete="SET NULL"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_limit_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    server_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    snapshots: Mapped[list[TestQuestionSnapshot]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_test_sessions_user_created", "user_id", "created_at"),)


class TestQuestionSnapshot(Base):
    """One frozen question inside a test session (doc 03 §2.4).

    SNAPSHOT RULE (hard): the text, options, correct answer and
    evidence state are COPIED here at creation time. A later bank
    edit, correction, or question deletion never changes this
    row — ``question_id`` is a link for review/navigation only
    (SET NULL if the source question is later deleted; the
    snapshot still stands). ``correct_index = -1`` means the
    question was explicitly included as UNKNOWN (only possible
    with ``include_unknown`` at creation); such a question must
    never be offered as a scored question (M7 enforces this).
    """

    __tablename__ = "test_question_snapshots"

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("test_sessions.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("extracted_questions.id", ondelete="SET NULL"), nullable=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[dict[str, Any]]] = mapped_column(JSONVariant, nullable=False)
    correct_index: Mapped[int] = mapped_column(Integer, nullable=False)
    answer_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = _created_at()

    session: Mapped[TestSession] = relationship(back_populates="snapshots")

    __table_args__ = (
        Index("ix_snapshots_session_position", "session_id", "position", unique=True),
        Index("ix_snapshots_session", "session_id", "created_at"),
    )


class StudentResponse(Base):
    """One saved answer inside an exam attempt (doc 03 §2.5, M7).

    One row per (session, snapshot) — the UNIQUE constraint makes
    every periodic save an upsert, never a second row. Responses
    are stored against SNAPSHOT ids, never live bank question
    ids, so a later bank edit cannot rewrite an attempt.
    ``selected_index`` NULL means unattempted (including a cleared
    response — the row is kept, so a mark-for-review flag survives
    a clear). A response on an UNKNOWN snapshot (correct_index
    -1) is stored but never scored (submit excludes it).
    """

    __tablename__ = "student_responses"

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("test_sessions.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("test_question_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    selected_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    marked_for_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = _updated_at()

    __table_args__ = (
        UniqueConstraint("session_id", "snapshot_id", name="uq_response_session_snapshot"),
        Index("ix_student_responses_session", "session_id", "updated_at"),
        Index("ix_student_responses_user_created", "user_id", "updated_at"),
    )


class TestResult(Base):
    """One stored result row per submitted session (doc 03 §2.5, M7).

    Computed on the backend at submit time from
    ``student_responses`` + snapshots + the session's marking
    config, and stored. The frontend never computes or supplies
    marks. ``session_id`` is UNIQUE: a duplicate submit returns
    this same row, never a second one. ``unknown_count`` is an
    M7 addition to doc 03's table (doc 03 lists no unknown
    count): snapshots with correct_index -1 are excluded from
    correct/incorrect/unattempted AND from max_marks, and are
    counted here instead — they are never scored as wrong and
    never raise into a 500. ``percentage`` is total/max clamped
    to [0, 100] (negative marking can make total_marks negative;
    a negative percentage is meaningless to a student).
    ``subject_breakdown`` / ``topic_breakdown`` are computed at
    submit time from the saved attempt (M8); M7 rows stored NULL
    and are backfilled on read (see services/results.py).
    """

    __tablename__ = "test_results"

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("test_sessions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False)
    incorrect_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unattempted_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unknown_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_marks: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    max_marks: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    time_taken_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    subject_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    topic_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    marking_config_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("marking_configs.id", ondelete="SET NULL"), nullable=False
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (Index("ix_test_results_user_created", "user_id", "created_at"),)


class StudentQuestionCollection(Base):
    """One bookmark / mistake / custom entry in a student's
    question collection (doc 03 §2.3, M8, GAP-8).

    ONE table serves bookmarks and the mistake notebook,
    distinguished by ``collection_type`` — no second table.
    A "mistake" row is created by the submit flow (M8) when a
    student answers a scored question incorrectly; it is the
    same table as bookmarks so one query serves both lists.
    ``question_id`` is a live link to the bank question
    (ON DELETE CASCADE): the notebook shows the CURRENT bank
    text. The PRACTICE test built from mistakes does NOT use
    the live bank — its snapshots are copied from the ORIGINAL
    attempt snapshots (see services/results.py), so a later
    bank correction never changes a practice test.
    UNIQUE(user, question, type): a student bookmarks a
    question once; the submit flow never writes a duplicate
    mistake row for the same question.
    """

    __tablename__ = "student_question_collections"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("extracted_questions.id", ondelete="CASCADE"), nullable=False
    )
    collection_type: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "question_id",
            "collection_type",
            name="uq_collection_user_question_type",
        ),
        CheckConstraint(
            "collection_type IN ('bookmark', 'mistake', 'custom')",
            name="ck_collection_type",
        ),
        Index("ix_collections_user_type_created", "user_id", "collection_type", "created_at"),
        Index("ix_collections_question", "question_id", "created_at"),
    )
