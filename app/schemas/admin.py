# OfficerPath AI — Phase 2, M9
# Admin schemas (GAP-10). Read-only views over real engine rows.

from pydantic import BaseModel, Field


class AdminOverview(BaseModel):
    users: int
    documents: int
    jobs: int
    jobs_by_status: dict[str, int]
    questions: int
    tests: int
    results: int
    errors: int
    notifications: int


class AdminUserItem(BaseModel):
    user_id: str
    full_name: str
    phone: str | None = None
    preferred_exam: str | None = None
    education_level: str | None = None
    documents: int
    tests: int
    created_at: str | None = None
    updated_at: str | None = None


class AdminUserListResponse(BaseModel):
    items: list[AdminUserItem]
    total: int
    limit: int = Field(default=20)
    offset: int = Field(default=0)


class AdminDocumentItem(BaseModel):
    id: str
    user_id: str
    title: str
    file_type: str
    file_size_bytes: int
    page_count: int | None = None
    latest_job_status: str | None = None
    is_shared: bool = False
    deleted_at: str | None = None
    created_at: str | None = None


class DocumentSharingRequest(BaseModel):
    """Admin-only (M11): mark a document shared / unshared."""

    is_shared: bool


class DocumentSharingResponse(BaseModel):
    id: str
    user_id: str
    title: str
    is_shared: bool


class AdminDocumentListResponse(BaseModel):
    items: list[AdminDocumentItem]
    total: int
    limit: int = Field(default=20)
    offset: int = Field(default=0)


class AdminJobItem(BaseModel):
    id: str
    user_id: str
    document_id: str
    document_title: str | None = None
    status: str
    retry_count: int
    error: str | None = None
    error_rows: int
    result_summary: dict | None = None
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class AdminJobListResponse(BaseModel):
    items: list[AdminJobItem]
    total: int
    limit: int = Field(default=20)
    offset: int = Field(default=0)


class AdminErrorItem(BaseModel):
    id: str
    document_id: str
    document_title: str | None = None
    job_id: str | None = None
    page_number: int | None = None
    stage: str | None = None
    error_code: str
    message: str
    created_at: str | None = None


class AdminErrorListResponse(BaseModel):
    items: list[AdminErrorItem]
    total: int
    limit: int = Field(default=20)
    offset: int = Field(default=0)


class AdminQuestionItem(BaseModel):
    id: str
    document_id: str
    question_number: str | None = None
    text: str
    options_count: int
    correct_index: int
    answer_status: str | None = None
    validation_status: str
    extraction_method: str | None = None
    created_at: str | None = None


class AdminQuestionListResponse(BaseModel):
    items: list[AdminQuestionItem]
    total: int
    limit: int = Field(default=20)
    offset: int = Field(default=0)
