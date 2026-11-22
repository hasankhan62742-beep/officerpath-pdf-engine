# OfficerPath AI — Phase 1, M7
# Async-jobs API schemas: submit a document for background
# processing, then poll its status. The parse itself happens in
# the worker (app/workers), not in the request.

from __future__ import annotations

from pydantic import BaseModel


class AsyncJobCreatedResponse(BaseModel):
    job_id: str
    document_id: str
    status: str = "queued"
    filename: str
    page_count: int | None = None


class AsyncJobStageResponse(BaseModel):
    stage: str
    status: str
    detail: dict | None = None
    created_at: str | None = None


class AsyncJobStatusResponse(BaseModel):
    job_id: str
    document_id: str
    status: str
    retry_count: int
    error: str | None = None
    result_summary: dict | None = None
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    stages: list[AsyncJobStageResponse] = []
