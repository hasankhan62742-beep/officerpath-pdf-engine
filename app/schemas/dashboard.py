# OfficerPath AI — Phase 2, M4
# Schemas for the dashboard + document listing/detail endpoints.
# All values come from real engine-DB rows; counts are real counts
# (a zero is a measured zero, never a placeholder).

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.documents import DocumentResponse, JobResponse


class DashboardDocumentItem(BaseModel):
    """One document in a list, with its latest job attached.
    `questions`/`answered` come from the job's result_summary when
    the job is done — None while the job has not produced them."""

    id: str
    title: str
    file_type: str
    file_size_bytes: int
    page_count: int | None = None
    created_at: str
    job: JobResponse | None = None
    questions: int | None = None
    answered: int | None = None


class DocumentListResponse(BaseModel):
    documents: list[DashboardDocumentItem]
    total: int
    limit: int
    offset: int


class JobStageItem(BaseModel):
    stage: str
    status: str
    detail: dict | None = None
    created_at: str | None = None


class JobDetailResponse(JobResponse):
    """JobResponse plus the fields the detail page needs: the
    result summary (question counts, timings) — the raw summary is
    the engine's own record, not a frontend computation."""

    result_summary: dict | None = None


class DocumentDetailResponse(BaseModel):
    document: DocumentResponse
    job: JobDetailResponse | None = None
    stages: list[JobStageItem] = []


class DashboardSummaryResponse(BaseModel):
    """Real dashboard numbers only: the document total and the job
    counts by status for the signed-in user's non-deleted
    documents, plus the newest documents. No test-result numbers
    yet — no test_results rows exist in Phase 2 until M7/M8, so
    the dashboard does not invent that section."""

    documents_total: int
    jobs_by_status: dict[str, int]
    recent_documents: list[DashboardDocumentItem] = Field(default_factory=list)


class DocumentDeleteResponse(BaseModel):
    document_id: str
    deleted: bool = True
    job_cancelled: bool = False
