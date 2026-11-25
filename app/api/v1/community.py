# OfficerPath AI — PDF Engine (M16)
# Community-contributed questions ("Add Questions").
#
# A student submits a question + 4 options + correct answer +
# explanation + subject + source + paper; it waits (pending)
# until an admin approves it. Only approved questions reach
# the bank. Every route requires a valid Supabase JWT; a user
# reads only their own submissions (never leaks existence).

from contextlib import contextmanager

from fastapi import APIRouter, Depends, Query

from app.core.errors import ApiError
from app.db.session import get_session
from app.schemas.community import (
    CommunityQuestionCreate,
    CommunityQuestionCreateResponse,
    CommunityQuestionListResponse,
)
from app.security.dependencies import get_current_user
from app.services import community as community_service

router = APIRouter(prefix="/api/v1/community", tags=["community"])

MAX_LIST_LIMIT = 100


@contextmanager
def _session_or_503():
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


@router.post(
    "/questions",
    response_model=CommunityQuestionCreateResponse,
    status_code=201,
)
async def submit_question(
    payload: CommunityQuestionCreate,
    user: dict = Depends(get_current_user),
) -> CommunityQuestionCreateResponse:
    """Submit one question for review. 422 on bad fields, 409
    when the same question is already submitted or already in
    the bank for that subject, 429 past 20 submissions a day."""
    with _session_or_503() as session:
        result = community_service.submit_question(session, user, payload.model_dump())
    return CommunityQuestionCreateResponse(**result)


@router.get("/questions/mine", response_model=CommunityQuestionListResponse)
async def list_my_questions(
    limit: int = Query(20, ge=1, le=MAX_LIST_LIMIT),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
) -> CommunityQuestionListResponse:
    """The caller's own submissions with their review status
    (pending / approved / rejected + the admin's note)."""
    with _session_or_503() as session:
        result = community_service.list_mine(session, user, limit=limit, offset=offset)
    return CommunityQuestionListResponse(**result)
