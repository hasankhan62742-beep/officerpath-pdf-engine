# OfficerPath AI — PDF Engine (Phase 1, M6)
# Schemas for the review API: synchronous parse, review list,
# manual corrections, stored report.

from __future__ import annotations

from pydantic import BaseModel, Field


class ReviewItemResponse(BaseModel):
    question_id: str
    document_id: str
    number: str | None
    text: str
    options: list[str]
    status: str  # pending | unknown
    page: int | None


class ReviewListResponse(BaseModel):
    job_id: str
    items: list[ReviewItemResponse]
    count: int


class CorrectionRequest(BaseModel):
    field: str = Field(description="question_text | option_text:<0-3> | answer (letter A-D)")
    new_value: str
    reason: str = ""


class CorrectionResponse(BaseModel):
    question_id: str
    number: str | None
    field: str
    old_value: str | None
    new_value: str
    validation_status: str
    validation_issues: list[dict]


class DocumentReportResponse(BaseModel):
    document_id: str
    job_id: str | None
    rule_set_version: str
    questions_extracted: int
    questions_missing_options: int
    uncertain_answers: int
    conflicting_answers: int
    unmatched_key_entries: int
    duplicates_found: int
    requires_review: bool
    review_reasons: list[str]
    summary: dict
    created_at: str | None


class ParseResponse(BaseModel):
    document_id: str
    job_id: str | None
    persisted: bool
    filename: str
    is_digital: bool
    page_count: int
    matched: dict
    report: dict
    debug: dict
