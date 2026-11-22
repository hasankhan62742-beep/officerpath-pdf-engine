# OfficerPath AI — Phase 2, M8
# Results history (GAP-7): the student's submitted results,
# newest first. Values are the stored test_results rows,
# exactly — the frontend never recomputes marks. Breakdowns
# are shown as stored (an M7 row keeps NULL until its detail
# page backfills it).

from fastapi import APIRouter, Depends, Query

from app.api.v1.tests import _session_or_503
from app.schemas.results import ResultsListResponse
from app.security.dependencies import get_current_user
from app.services import results as results_service

router = APIRouter(prefix="/api/v1", tags=["results"])

MAX_LIST_LIMIT = 100
DEFAULT_RESULTS_LIMIT = 20


@router.get("/results", response_model=ResultsListResponse)
async def list_results(
    limit: int = Query(DEFAULT_RESULTS_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
) -> ResultsListResponse:
    with _session_or_503() as session:
        result = results_service.list_results(session, user, limit=limit, offset=offset)
    return ResultsListResponse(**result)
