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

from app.schemas.tests import MarkingConfigResponse, SnapshotItem


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
    snapshots: list[SnapshotItem]
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
