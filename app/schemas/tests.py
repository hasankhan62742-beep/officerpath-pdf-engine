# OfficerPath AI — Phase 2, M6
# Schemas for the test builder (GAP-5).
#
# Rules baked into the shapes:
# - A test stores its marking config id AND the frozen snapshot
#   rows; the frontend never computes marks (M7/M8 do it on the
#   backend from the snapshots + the session's config).
# - ``correct_index`` -1 in a snapshot means the question was
#   explicitly included as UNKNOWN (``include_unknown`` at
#   creation); the UI renders it as unknown, never as a correct
#   option, and M7 must never offer it as a scored question.
# - ``correct_index`` None means the key is WITHHELD: the test
#   has not been submitted yet, so the detail endpoints return
#   no key (security fix — a student must not read the key
#   mid-test). ``is_unknown`` still flags the -1 rows.
# - Question counts are 1–200 (validated in the service); the UI
#   offers 25/50/100/150/200 as quick picks. No duplicates in a
#   test unless ``allow_repetition`` is explicitly true.

from __future__ import annotations

from pydantic import BaseModel


class MarkingConfigResponse(BaseModel):
    id: str
    name: str
    correct_marks: float
    incorrect_marks: float
    unattempted_marks: float
    is_default: bool


class MarkingConfigCreate(BaseModel):
    name: str
    correct_marks: float
    incorrect_marks: float
    unattempted_marks: float


class MarkingConfigListResponse(BaseModel):
    marking_configs: list[MarkingConfigResponse]
    total: int


class SnapshotOption(BaseModel):
    label: str
    text: str


class SnapshotItem(BaseModel):
    snapshot_id: str
    question_id: str | None
    position: int
    question_text: str
    options: list[SnapshotOption]
    # None = key withheld: the test has not been submitted yet.
    # -1 = UNKNOWN (explicit opt-in only); >= 0 = the answer.
    correct_index: int | None
    answer_source: str | None
    # Stored verbatim explanation, frozen at test creation (M10).
    # None pre-submit (withheld with the key — never leaked
    # mid-test) or when no explanation was stored at all.
    explanation: str | None = None
    # True when the frozen correct_index is -1. Always present,
    # so the UI can flag unknown questions without the key.
    is_unknown: bool = False
    source_document_id: str | None
    source_page: int | None


class TestResponse(BaseModel):
    test_id: str
    template_id: str
    title: str
    description: str | None
    question_count: int
    source_type: str
    source_ids: dict | None
    allow_repetition: bool
    include_unknown: bool
    status: str
    marking_config: MarkingConfigResponse
    created_at: str | None
    updated_at: str | None


class TestDetailResponse(TestResponse):
    snapshots: list[SnapshotItem]
    excluded_unknown: int
    excluded_no_options: int
    # M8 only: retry provenance / from-mistakes skips. Absent
    # (None) on tests built the normal way.
    retried_from_test_id: str | None = None
    skipped_question_ids: list[str] | None = None


class TestListResponse(BaseModel):
    tests: list[TestResponse]
    total: int
    limit: int
    offset: int


class TestCreateRequest(BaseModel):
    name: str
    description: str | None = None
    question_count: int
    source_type: str  # all | documents | subjects | topics | mixed | explicit
    source_ids: dict | list[str] | None = None
    marking_config_id: str | None = None
    marking: MarkingConfigCreate | None = None
    allow_repetition: bool = False
    include_unknown: bool = False
    time_limit_seconds: int | None = None
    # M12 — question range (1-based, inclusive positions into the
    # chosen section's bank-ordered candidate pool). Only valid
    # with source_type "topics" and exactly ONE topic id; both
    # must be given together. The maximum is the section's live
    # available count — there is no fixed cap.
    question_range_start: int | None = None
    question_range_end: int | None = None


class TestUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class AvailabilitySampleItem(BaseModel):
    question_id: str
    document_id: str
    document_title: str
    number: str | None
    text: str
    correct_index: int  # -1 = UNKNOWN (only when include_unknown)


class TopicAvailability(BaseModel):
    """M12 — per-topic counts for one requested topic id.
    Returned only when source_type is "topics" and no range is
    given. Topics with no available questions are included
    with available 0, so the UI can show every section tab."""

    topic_id: str
    topic_name: str
    available: int
    excluded_unknown: int
    excluded_no_options: int


class AvailabilityResponse(BaseModel):
    available: int
    excluded_unknown: int
    excluded_no_options: int
    sample: list[AvailabilitySampleItem]
    by_topic: list[TopicAvailability] | None = None


class ScoreItem(BaseModel):
    correct_index: int
    selected_index: int | None


class ScoreResponse(BaseModel):
    total_questions: int
    correct: int
    incorrect: int
    unattempted: int
    total_marks: float
    max_marks: float
