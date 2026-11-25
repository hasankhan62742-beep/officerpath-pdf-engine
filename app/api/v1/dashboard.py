# OfficerPath AI — Phase 2, M4
# Dashboard summary (real database values only — no static demo
# numbers, no invented totals). The numbers are the engine DB's
# own counts for the signed-in user; a zero is a measured zero.
#
# No test-result numbers are returned: no test_results rows exist
# in Phase 2 until M7/M8, so the dashboard does not invent that
# section (doc 03 §2.5, doc 05 §8).

from contextlib import contextmanager

from fastapi import APIRouter, Depends

from app.core.errors import ApiError
from app.database.sqlalchemy_repositories import (
    SqlAlchemyDocumentRepository,
    SqlAlchemyJobRepository,
)
from app.db.session import get_session
from app.schemas.dashboard import DashboardDocumentItem, DashboardSummaryResponse
from app.security.dependencies import get_current_user
from app.services import documents as document_service

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@contextmanager
def _repositories():
    """Engine-DB repositories for one request (ADR-011)."""
    session = get_session()
    if session is None:
        raise ApiError(
            status_code=503,
            code="database_unavailable",
            message="The database is not configured on this server.",
        )
    try:
        yield (
            session,
            SqlAlchemyDocumentRepository(session),
            SqlAlchemyJobRepository(session),
        )
    finally:
        session.close()


@router.get("/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(
    user: dict = Depends(get_current_user),
) -> DashboardSummaryResponse:
    with _repositories() as (session, documents, jobs):
        summary = document_service.get_dashboard_summary(user, documents, jobs, session=session)
    return DashboardSummaryResponse(
        documents_total=summary["documents_total"],
        jobs_by_status=summary["jobs_by_status"],
        recent_documents=[DashboardDocumentItem(**item) for item in summary["recent_documents"]],
    )
