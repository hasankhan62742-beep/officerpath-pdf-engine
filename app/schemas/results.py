# OfficerPath AI — Phase 2, M8
# Schemas for results + analytics (GAP-7) and question
# collections (GAP-8).
#
# Rules baked into the shapes:
# - The result detail is the STORED test_results row, exactly —
#   the frontend never recomputes marks. Breakdowns come from
#   the saved attempt only; a question with no subject link
#   lands in the "Uncategorised" bucket, never a forced
#   category.
# - Review items show ONLY what the engine stored (snapshot
#   text/options/correct answer + the student's selection +
#   the evidence source + the stored verbatim explanation).
#   No explanations are invented: None means the source gave
#   none, and the UI shows nothing then.
# - Unknown snapshots (correct_index -1) show as status
#   "unknown", never correct/incorrect.

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.exam import TestResultResponse
from app.schemas.tests import MarkingConfigCreate


class BreakdownItem(BaseModel):
    key: str
    name: str
    slug: str | None
    scored: int
    correct: int
    incorrect: int
    unattempted: int
    marks: float
    max_marks: float
    accuracy: float | None


class WeakStrongArea(BaseModel):
    subject_name: str
    accuracy: float | None
    scored: int


class ReviewItem(BaseModel):
    snapshot_id: str
    question_id: str | None
    position: int
    question_text: str
    options: list[dict]
    correct_index: int
    selected_index: int | None
    marked_for_review: bool
    status: str  # correct | incorrect | unattempted | unknown
    answer_source: str | None
    # Stored verbatim explanation from the snapshot (M10).
    # None = the source gave none; the UI shows nothing then.
    explanation: str | None = None
    source_document_id: str | None
    source_page: int | None
    is_bookmarked: bool
    bookmark_id: str | None
    is_mistake: bool


class TestResultDetailResponse(TestResultResponse):
    subject_breakdown: list[BreakdownItem] | None
    topic_breakdown: list[BreakdownItem] | None
    weak_areas: list[WeakStrongArea]
    strong_areas: list[WeakStrongArea]
    review: list[ReviewItem]


class TestResultListItem(TestResultResponse):
    subject_breakdown: list[BreakdownItem] | None
    topic_breakdown: list[BreakdownItem] | None
    weak_areas: list[WeakStrongArea]
    strong_areas: list[WeakStrongArea]


class ResultsListResponse(BaseModel):
    results: list[TestResultListItem]
    total: int
    limit: int
    offset: int


class FromMistakesRequest(BaseModel):
    name: str
    question_ids: list[str] | None = None
    time_limit_seconds: int | None = None
    marking_config_id: str | None = None
    marking: MarkingConfigCreate | None = None


class CollectionQuestion(BaseModel):
    question_id: str
    document_id: str
    document_title: str
    number: str | None
    text: str
    options: list[str]
    correct_index: int
    answer_source: str
    # Stored verbatim explanation from the bank question (M10).
    # None = the source gave none; the UI shows nothing then.
    explanation: str | None = None


class CollectionItem(BaseModel):
    id: str
    question_id: str
    collection_type: str
    note: str | None
    created_at: str | None
    updated_at: str | None
    question: CollectionQuestion | None
    already_exists: bool | None = None


class CollectionListResponse(BaseModel):
    collections: list[CollectionItem]
    total: int
    limit: int
    offset: int


class CollectionCreateRequest(BaseModel):
    question_id: str
    collection_type: str  # bookmark | custom ('mistake' is 422)
    note: str | None = None


class CollectionNoteRequest(BaseModel):
    note: str | None = None
