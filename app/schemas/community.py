# OfficerPath AI — PDF Engine (M16)
# Schemas for community-contributed questions ("Add Questions").
#
# Truth rules baked into the shapes:
# - ``correct_index`` is 0..3, always — a submission without
#   exactly one correct option is refused, never stored with a
#   guessed key.
# - ``contributor_name`` is a display name only (profile full
#   name, else the email local part). A full email address is
#   NEVER exposed in any response.
# - ``status`` is pending | approved | rejected; only approved
#   rows ever reach the bank.

from __future__ import annotations

from pydantic import BaseModel, Field


class CommunityQuestionCreate(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    options: list[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    explanation: str | None = Field(default=None, max_length=5000)
    subject_id: str
    topic_id: str | None = None
    source: str | None = Field(default=None, max_length=500)
    # The paper the question appeared in, as exact as the
    # contributor knows it (e.g. "PPSC Tehsildar BS-16 2021").
    # Optional — a contributor may not know it — but the form
    # asks for it, and the duplicate check runs on the question
    # text either way.
    paper: str | None = Field(default=None, max_length=200)


class CommunitySubjectRef(BaseModel):
    subject_id: str | None
    subject_name: str | None
    subject_slug: str | None
    topic_id: str | None
    topic_name: str | None


class CommunityQuestionItem(BaseModel):
    id: str
    question: str
    options: list[str]
    correct_index: int
    correct_letter: str
    explanation: str | None = None
    subject: CommunitySubjectRef
    source: str | None = None
    paper: str | None = None
    status: str  # pending | approved | rejected
    review_note: str | None = None
    contributor_name: str
    bank_question_id: str | None = None
    created_at: str | None = None


class CommunityQuestionCreateResponse(BaseModel):
    id: str
    status: str
    contributor_name: str
    created_at: str | None = None


class CommunityQuestionListResponse(BaseModel):
    items: list[CommunityQuestionItem]
    total: int
    limit: int = 20
    offset: int = 0


class CommunityReviewRequest(BaseModel):
    approved: bool
    note: str | None = Field(default=None, max_length=1000)
