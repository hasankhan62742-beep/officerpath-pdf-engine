# OfficerPath AI — Phase 2, M6
# Test builder (GAP-5) + marking configs.
#
# M7 adds the examination interface (GAP-6) on the same
# router: start, exam session, answers, submit, result. The
# session IS the test instance (M6 creates template + session
# 1:1); start activates it, submit writes exactly one stored
# result row. All routes require a valid Supabase JWT; every
# read/write filters by the JWT's user id and answers 404 for
# unknown or another user's tests (never leaks existence).
# Values come from the engine DB only (ADR-011) — no PostgREST,
# no fake data. Creating a test writes template + session +
# frozen snapshots in one transaction; a later bank edit never
# changes a snapshot. Marking is stored with the test and
# computed on the backend (M7/M8) — never in the browser.

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.session import get_session
from app.schemas.exam import (
    ExamSessionResponse,
    SaveAnswersRequest,
    SaveAnswersResponse,
    StartTestResponse,
    TestResultResponse,
)
from app.schemas.questions import QuestionListResponse
from app.schemas.results import FromMistakesRequest, TestResultDetailResponse
from app.schemas.tests import (
    AvailabilityResponse,
    MarkingConfigCreate,
    MarkingConfigListResponse,
    MarkingConfigResponse,
    TestCreateRequest,
    TestDetailResponse,
    TestListResponse,
    TestResponse,
    TestUpdateRequest,
)
from app.security.dependencies import get_current_user
from app.services import exam as exam_service
from app.services import results as results_service
from app.services import tests as test_service

router = APIRouter(prefix="/api/v1", tags=["tests"])

MAX_LIST_LIMIT = 100
DEFAULT_TEST_LIMIT = 20


@contextmanager
def _session_or_503() -> Iterator[Session]:
    """Engine-DB session for one request (ADR-011)."""
    session = get_session()
    if session is None:
        raise ApiError(
            status_code=503,
            code="database_unavailable",
            message="The database is not configured on this server.",
        )
    try:
        yield session
    finally:
        session.close()


@router.get("/marking-configs", response_model=MarkingConfigListResponse)
async def list_marking_configs(
    user: dict = Depends(get_current_user),
) -> MarkingConfigListResponse:
    with _session_or_503() as session:
        return MarkingConfigListResponse(**test_service.list_marking_configs(session))


@router.post("/marking-configs", response_model=MarkingConfigResponse)
async def create_marking_config(
    payload: MarkingConfigCreate,
    user: dict = Depends(get_current_user),
) -> MarkingConfigResponse:
    with _session_or_503() as session:
        result = test_service.create_marking_config(session, user, payload.model_dump())
    return MarkingConfigResponse(**result)


@router.get("/tests/availability", response_model=AvailabilityResponse)
async def test_availability(
    source_type: str = Query(..., description="all | documents | subjects | topics | mixed"),
    document_ids: list[str] | None = Query(None, description="Document ids (documents/mixed)."),
    subject_ids: list[str] | None = Query(None, description="Subject ids (subjects/mixed)."),
    topic_ids: list[str] | None = Query(None, description="Topic ids (topics)."),
    include_unknown: bool = Query(
        False, description="Count unknown-answer questions as available."
    ),
    question_range_start: int | None = Query(
        None,
        description="M12: range start, 1-based inclusive, single-topic only.",
    ),
    question_range_end: int | None = Query(
        None,
        description="M12: range end, 1-based inclusive, single-topic only.",
    ),
    counts_only: bool = Query(
        False,
        description="Read view only: return per-topic counts from one "
        "aggregate query, without resolving the pool or a sample. "
        "Only valid with source_type 'topics' and no range.",
    ),
    user: dict = Depends(get_current_user),
) -> AvailabilityResponse:
    if source_type == "documents":
        source_ids: dict | list[str] | None = document_ids
    elif source_type == "subjects":
        source_ids = subject_ids
    elif source_type == "topics":
        source_ids = topic_ids
    elif source_type == "mixed":
        source_ids = {
            "document_ids": document_ids or [],
            "subject_ids": subject_ids or [],
        }
    elif source_type == "all":
        source_ids = None
    else:
        raise ApiError(
            status_code=422,
            code="validation_error",
            message="source_type must be one of: all, documents, subjects, topics, mixed.",
        )
    with _session_or_503() as session:
        result = test_service.availability(
            session,
            user,
            source_type=source_type,
            source_ids=source_ids,
            include_unknown=include_unknown,
            question_range_start=question_range_start,
            question_range_end=question_range_end,
            counts_only=counts_only,
        )
    return AvailabilityResponse(**result)


@router.get("/tests/sections/questions", response_model=QuestionListResponse)
async def list_section_questions(
    topic_ids: list[str] = Query(..., description="Topic ids of one section (one or more)."),
    limit: int = Query(20, ge=1, le=MAX_LIST_LIMIT),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
) -> QuestionListResponse:
    """M12 reading mode: the section's available questions in
    bank order, with options + the stored answer + the stored
    explanation. Same pool as a test from these topics, so a
    reading range of 1..N maps exactly onto a test range."""
    with _session_or_503() as session:
        result = test_service.list_section_questions(
            session, user, topic_ids=topic_ids, limit=limit, offset=offset
        )
    return QuestionListResponse(**result)


@router.post("/tests", response_model=TestDetailResponse, status_code=201)
async def create_test(
    payload: TestCreateRequest,
    user: dict = Depends(get_current_user),
) -> TestDetailResponse:
    with _session_or_503() as session:
        result = test_service.create_test(session, user, payload.model_dump())
    return TestDetailResponse(**result)


@router.get("/tests", response_model=TestListResponse)
async def list_tests(
    limit: int = Query(DEFAULT_TEST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
) -> TestListResponse:
    with _session_or_503() as session:
        result = test_service.list_tests(session, user, limit=limit, offset=offset)
    return TestListResponse(**result)


@router.post("/tests/from-mistakes", response_model=TestDetailResponse, status_code=201)
async def create_test_from_mistakes(
    payload: FromMistakesRequest,
    user: dict = Depends(get_current_user),
) -> TestDetailResponse:
    with _session_or_503() as session:
        result = results_service.create_test_from_mistakes(session, user, payload.model_dump())
    return TestDetailResponse(**result)


@router.post("/tests/{test_id}/retry", response_model=TestDetailResponse, status_code=201)
async def retry_test(
    test_id: str,
    user: dict = Depends(get_current_user),
) -> TestDetailResponse:
    with _session_or_503() as session:
        result = results_service.retry_test(session, user, test_id)
    return TestDetailResponse(**result)


@router.get("/tests/{test_id}", response_model=TestDetailResponse)
async def get_test(
    test_id: str,
    user: dict = Depends(get_current_user),
) -> TestDetailResponse:
    with _session_or_503() as session:
        result = test_service.get_test(session, user, test_id)
    return TestDetailResponse(**result)


@router.patch("/tests/{test_id}", response_model=TestResponse)
async def update_test(
    test_id: str,
    payload: TestUpdateRequest,
    user: dict = Depends(get_current_user),
) -> TestResponse:
    with _session_or_503() as session:
        result = test_service.update_test(
            session, user, test_id, payload.model_dump(exclude_unset=True)
        )
    return TestResponse(**result)


@router.delete("/tests/{test_id}")
async def delete_test(
    test_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    with _session_or_503() as session:
        return test_service.delete_test(session, user, test_id)


# ---------------------------------------------------------------------------
# Examination interface (M7, GAP-6)
# ---------------------------------------------------------------------------


@router.post("/tests/{test_id}/start", response_model=StartTestResponse)
async def start_test(
    test_id: str,
    user: dict = Depends(get_current_user),
) -> StartTestResponse:
    with _session_or_503() as session:
        result = exam_service.start_test(session, user, test_id)
    return StartTestResponse(**result)


@router.get("/tests/{test_id}/session", response_model=ExamSessionResponse)
async def get_exam_session(
    test_id: str,
    user: dict = Depends(get_current_user),
) -> ExamSessionResponse:
    with _session_or_503() as session:
        result = exam_service.get_exam_session(session, user, test_id)
    return ExamSessionResponse(**result)


@router.post("/tests/{test_id}/answers", response_model=SaveAnswersResponse)
async def save_answers(
    test_id: str,
    payload: SaveAnswersRequest,
    user: dict = Depends(get_current_user),
) -> SaveAnswersResponse:
    with _session_or_503() as session:
        result = exam_service.save_answers(session, user, test_id, payload.model_dump())
    return SaveAnswersResponse(**result)


@router.post("/tests/{test_id}/submit", response_model=TestResultResponse)
async def submit_test(
    test_id: str,
    user: dict = Depends(get_current_user),
) -> TestResultResponse:
    with _session_or_503() as session:
        result = exam_service.submit_test(session, user, test_id)
    return TestResultResponse(**result)


@router.get("/tests/{test_id}/result", response_model=TestResultDetailResponse)
async def get_test_result(
    test_id: str,
    user: dict = Depends(get_current_user),
) -> TestResultDetailResponse:
    # M8: the stored row + breakdowns (backfilled when an M7
    # row stored NULL) + weak/strong areas + per-question review.
    with _session_or_503() as session:
        result = results_service.get_result_detail(session, user, test_id)
    return TestResultDetailResponse(**result)
