# OfficerPath AI — PDF Engine (Phase 1A)
# Pydantic v2 request/response schemas. All input validation lives here;
# the API layer never trusts a raw body.

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.config import settings


class FileType(str, Enum):
    pdf = "pdf"
    txt = "txt"
    docx = "docx"
    jpg = "jpg"
    jpeg = "jpeg"
    png = "png"
    webp = "webp"
    tiff = "tiff"
    tif = "tif"


class JobStatus(str, Enum):
    queued = "queued"
    uploading = "uploading"
    processing = "processing"
    # ADR-011 (M3): terminal status is `done`, matching the live
    # 015 check constraint. The engine used `completed` in M6/M7,
    # which the constraint rejects — no job could complete in
    # production. `completed` is gone from the job vocabulary
    # (PipelineStage.COMPLETED is a stage NAME, not a job status).
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class DocumentRegisterRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    storage_path: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="Path in the pdf-documents bucket, e.g. '<user_id>/abc.pdf'.",
    )
    file_type: FileType
    file_size_bytes: int = Field(..., gt=0, le=settings.max_file_size_bytes)
    page_count: int | None = Field(default=None, ge=1, le=settings.max_pages_per_job)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    # SHA-256 of the file bytes (M1 ingestion dedup). 64 hex chars when
    # present; absent for pre-M1 registrations.
    content_hash: str | None = Field(default=None, min_length=64, max_length=64)
    metadata: dict[str, Any] | None = None


class DocumentResponse(BaseModel):
    id: str
    user_id: str
    title: str
    storage_path: str
    file_type: str
    file_size_bytes: int
    page_count: int | None
    content_hash: str | None = None
    created_at: str


class JobResponse(BaseModel):
    id: str
    user_id: str
    document_id: str
    status: JobStatus
    retry_count: int
    error: str | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


class RegisterResponse(BaseModel):
    document: DocumentResponse
    job: JobResponse
    idempotent_replay: bool = False


class PageClassificationResponse(BaseModel):
    page_number: int
    classification: str
    method: str
    confidence: float | None = None
    width_px: int | None = None
    height_px: int | None = None
    dpi_estimate: float | None = None
    rotation_degrees: int | None = None
    note: str | None = None


class ValidationIssueResponse(BaseModel):
    code: str
    message: str
    severity: str = "error"


class UploadResponse(BaseModel):
    status: str  # stored | replay | rejected
    filename: str
    document: DocumentResponse | None = None
    job: JobResponse | None = None
    storage_path: str | None = None
    idempotent_replay: bool = False
    sha256: str
    pages: list[PageClassificationResponse] = []
    issues: list[ValidationIssueResponse] = []


class BatchUploadResponse(BaseModel):
    results: list[UploadResponse]
    stored: int
    replayed: int
    rejected: int


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class PageInventoryItem(BaseModel):
    """One page of a document's A3 inventory: classification +
    what extraction found on it. ``extraction_status`` is None
    when the page was never inventoried (parsed before A3)."""

    page_number: int
    classification: str
    extraction_status: str | None = None
    question_count: int = 0
    answered_count: int = 0
    unknown_count: int = 0
    pending_count: int = 0
    error_message: str | None = None


class PageInventoryResponse(BaseModel):
    """GET /documents/{id}/pages: the page inventory plus the
    completeness comparison. ``missing_question_count`` is None
    until the owner sets an expected count; ``missing_numbers``
    comes from the report's number-gap validation (capped at 20
    by the validator — see missing_numbers_truncated)."""

    document_id: str
    page_count: int
    expected_question_count: int | None = None
    extracted_question_count: int
    # Pending items are questions the parse found but could not
    # answer; they are stored as rows and counted in each page's
    # question_count, so they are reported separately here rather
    # than folded into extracted_question_count (the engine's
    # standing questions/pending split).
    pending_question_count: int
    missing_question_count: int | None = None
    missing_numbers: list[int] = []
    missing_numbers_truncated: bool = False
    zero_question_pages: list[int] = []
    low_confidence_pages: list[int] = []
    failed_pages: list[int] = []
    pages: list[PageInventoryItem] = []


class ExpectedCountRequest(BaseModel):
    """PATCH /documents/{id}: the owner's statement of how many
    questions the paper holds (None clears it). Never inferred."""

    expected_question_count: int | None = Field(default=None, ge=0, le=100_000)


class ExpectedCountResponse(BaseModel):
    document_id: str
    expected_question_count: int | None = None
    extracted_question_count: int
    missing_question_count: int | None = None


class PageRetryResponse(BaseModel):
    """POST /documents/{id}/pages/{page}/retry: the queued
    background job. ``existing_job`` is True when an identical
    retry was already queued/processing for that page."""

    job_id: str
    document_id: str
    page_number: int
    status: str
    existing_job: bool = False


class HealthResponse(BaseModel):
    status: str  # ok | degraded
    service: str
    version: str
    environment: str
    checks: dict[str, str]


class VersionResponse(BaseModel):
    service: str
    version: str
    git_commit: str | None
    environment: str
