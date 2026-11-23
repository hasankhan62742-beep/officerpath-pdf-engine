# OfficerPath AI — Phase 2, M7
# Schemas for the examination interface (GAP-6).
#
# Rules baked into the shapes:
# - The timer is server truth: ``remaining_seconds`` and
#   ``server_time`` are computed on the server from
#   ``server_started_at`` + the time limit. ``remaining_seconds``
#   is null for untimed tests — never a faked countdown.
# - Answers are stored against SNAPSHOT ids, never live bank
#   question ids. ``selected_index`` null clears the answer.
# - The result shape is the STORED test_results row (M8's
#   analytics UI reads it; M7 only shows counts + marks).

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.tests import MarkingConfigResponse, SnapshotOption


class StartTestResponse(BaseModel):
    test_id: str
    title: str
    status: str
    time_limit_seconds: int | None
    server_started_at: str
    expires_at: str | None
    remaining_seconds: int | None
    marking_config: MarkingConfigResponse


class ExamResponseItem(BaseModel):
    snapshot_id: str
    selected_index: int | None
    marked_for_review: bool
    answered_at: str | None
    updated_at: str | None


class SessionSnapshotItem(BaseModel):
    """A snapshot AS SEEN DURING THE EXAM.

    Deliberately carries NO ``correct_index`` and NO
    ``answer_source``: the session response is served to the
    student's browser while the test is in progress, and leaking
    the key there would let anyone read the answers from the
    network tab. The UI only needs to know whether the question
    is UNKNOWN (options disabled, "not scored" badge) — that is
    the ``is_unknown`` flag. The full ``SnapshotItem`` (with the
    key) is still returned by the test-detail and result
    endpoints, which run after the test is over (or are the
    creator's own preview).
    """

    snapshot_id: str
    question_id: str | None
    position: int
    question_text: str
    options: list[SnapshotOption]
    is_unknown: bool
    source_document_id: str | None
    source_page: int | None


class ExamSessionResponse(BaseModel):
    test_id: str
    title: str
    status: str
    time_limit_seconds: int | None
    server_started_at: str | None
    expires_at: str | None
    remaining_seconds: int | None
    server_time: str
    marking_config: MarkingConfigResponse
    snapshots: list[SessionSnapshotItem]
    responses: list[ExamResponseItem]


class AnswerItem(BaseModel):
    snapshot_id: str
    selected_index: int | None  # null clears the answer
    marked_for_review: bool | None = None


class SaveAnswersRequest(BaseModel):
    answers: list[AnswerItem]


class SaveAnswersResponse(BaseModel):
    test_id: str
    status: str
    remaining_seconds: int | None
    saved: list[ExamResponseItem]


class TestResultResponse(BaseModel):
    result_id: str
    test_id: str
    template_id: str | None
    title: str
    status: str
    total_questions: int
    correct: int
    incorrect: int
    unattempted: int
    unknown_count: int
    total_marks: float
    max_marks: float
    percentage: float
    time_taken_seconds: int
    marking_config: MarkingConfigResponse
    submitted_at: str | None
