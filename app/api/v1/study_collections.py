# OfficerPath AI — B1/B2
# Named study collections (GAP report §3/§4): the shared bank
# documents grouped by the ``collection`` value in their
# metadata — PPSC Past Paper 2026, Most Important Questions —
# Computer, Fact Book for PMS and CSS 2027.
#
# Auth split (user decision #1, 2026-11-25):
# - LIST + DETAIL are PUBLIC: they return collection names,
#   document titles and question counts only — no question text,
#   no answers, no user data — so the Main Page and the public
#   collections list can show them to every visitor.
# - QUESTIONS requires a valid Supabase JWT (``get_current_user``)
#   and 404s for any document that is not shared: opening a
#   paper's questions needs a login, exactly like the rest of
#   the study surface. The engine enforces this; the UI gate is
#   only a convenience.
#
# Read-only. No writes, no new tables, no migration.

from fastapi import APIRouter, Depends, Query

from app.api.v1.tests import _session_or_503
from app.schemas.questions import DocumentQuestionsResponse
from app.schemas.study_collections import StudyCollection, StudyCollectionListResponse
from app.security.dependencies import get_current_user
from app.services import study_collections as collection_service

router = APIRouter(prefix="/api/v1", tags=["study-collections"])

MAX_LIST_LIMIT = 100
DEFAULT_DOCUMENT_LIMIT = 50


@router.get("/study-collections", response_model=StudyCollectionListResponse)
async def list_study_collections() -> StudyCollectionListResponse:
    with _session_or_503() as session:
        return StudyCollectionListResponse(**collection_service.list_study_collections(session))


@router.get("/study-collections/{slug}", response_model=StudyCollection)
async def get_study_collection(slug: str) -> StudyCollection:
    with _session_or_503() as session:
        return StudyCollection(**collection_service.get_study_collection(session, slug))


@router.get(
    "/study-collections/{slug}/documents/{document_id}/questions",
    response_model=DocumentQuestionsResponse,
)
async def list_study_collection_document_questions(
    slug: str,
    document_id: str,
    limit: int = Query(DEFAULT_DOCUMENT_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
) -> DocumentQuestionsResponse:
    with _session_or_503() as session:
        result = collection_service.list_shared_document_questions(
            session, slug, document_id, limit=limit, offset=offset
        )
    return DocumentQuestionsResponse(**result)
