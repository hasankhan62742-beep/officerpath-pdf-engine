# OfficerPath AI — Phase 2, M9
# Admin API (GAP-10, doc 05 §4). Every route is behind
# ``require_admin`` — the claim comes ONLY from the verified
# Supabase JWT (app_metadata.is_admin). Non-admins get 404
# (no-leak), never a 403 that confirms the route exists.
# Read-only in M9, except the M11 document-sharing toggle
# (PATCH /documents/{id}/sharing) — the one admin write.
# Admin reads are not logged to the DB (they would flood it);
# denied attempts are logged by require_admin itself.

from fastapi import APIRouter, Depends, Query

from app.api.v1.tests import _session_or_503
from app.schemas.admin import (
    AdminDocumentListResponse,
    AdminErrorListResponse,
    AdminJobListResponse,
    AdminOverview,
    AdminQuestionListResponse,
    AdminUserListResponse,
    DocumentSharingRequest,
    DocumentSharingResponse,
)
from app.schemas.community import (
    CommunityQuestionItem,
    CommunityQuestionListResponse,
    CommunityReviewRequest,
)
from app.security.dependencies import require_admin
from app.services import admin as admin_service
from app.services import community as community_service

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

MAX_LIST_LIMIT = 100
DEFAULT_LIMIT = 20


@router.get("/overview", response_model=AdminOverview)
async def get_overview(user: dict = Depends(require_admin)) -> AdminOverview:
    with _session_or_503() as session:
        return AdminOverview(**admin_service.overview(session))


@router.get("/users", response_model=AdminUserListResponse)
async def get_users(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_admin),
) -> AdminUserListResponse:
    with _session_or_503() as session:
        return AdminUserListResponse(
            **admin_service.list_users(session, limit=limit, offset=offset)
        )


@router.get("/documents", response_model=AdminDocumentListResponse)
async def get_documents(
    user_id: str | None = Query(None, description="Filter by owner user id."),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_admin),
) -> AdminDocumentListResponse:
    with _session_or_503() as session:
        return AdminDocumentListResponse(
            **admin_service.list_documents(session, user_id=user_id, limit=limit, offset=offset)
        )


@router.patch("/documents/{document_id}/sharing", response_model=DocumentSharingResponse)
async def set_document_sharing(
    document_id: str,
    payload: DocumentSharingRequest,
    user: dict = Depends(require_admin),
) -> DocumentSharingResponse:
    """Mark a document shared / unshared (M11). Sharing makes
    its questions visible to every authenticated student in the
    test pool (read-only); unsharing removes them at once.
    Non-admins get 404 (no-leak), same as every admin route."""
    with _session_or_503() as session:
        return DocumentSharingResponse(
            **admin_service.set_document_sharing(
                session, document_id=document_id, is_shared=payload.is_shared
            )
        )


@router.get("/jobs", response_model=AdminJobListResponse)
async def get_jobs(
    status: str | None = Query(
        None, description="Filter: queued | processing | done | failed | cancelled."
    ),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_admin),
) -> AdminJobListResponse:
    with _session_or_503() as session:
        return AdminJobListResponse(
            **admin_service.list_jobs(session, status=status, limit=limit, offset=offset)
        )


@router.get("/errors", response_model=AdminErrorListResponse)
async def get_errors(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_admin),
) -> AdminErrorListResponse:
    with _session_or_503() as session:
        return AdminErrorListResponse(
            **admin_service.list_errors(session, limit=limit, offset=offset)
        )


@router.get("/questions", response_model=AdminQuestionListResponse)
async def get_questions(
    validation_status: str | None = Query(
        None, description="Filter: unreviewed | approved | rejected."
    ),
    document_id: str | None = Query(None, description="Filter by source document id."),
    search: str | None = Query(None, description="Substring match on the question text."),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_admin),
) -> AdminQuestionListResponse:
    with _session_or_503() as session:
        return AdminQuestionListResponse(
            **admin_service.list_questions(
                session,
                validation_status=validation_status,
                document_id=document_id,
                search=search,
                limit=limit,
                offset=offset,
            )
        )


@router.get("/community/questions", response_model=CommunityQuestionListResponse)
async def get_community_questions(
    status: str | None = Query(None, description="Filter: pending | approved | rejected."),
    subject_id: str | None = Query(None, description="Filter by subject id."),
    search: str | None = Query(None, description="Substring match on the question text."),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_admin),
) -> CommunityQuestionListResponse:
    """M16 review queue, pending first. Each item carries its
    paper, source and contributor name — the paper is what lets
    the admin spot a repetition at review time."""
    with _session_or_503() as session:
        return CommunityQuestionListResponse(
            **community_service.list_for_admin(
                session,
                status=status,
                subject_id=subject_id,
                search=search,
                limit=limit,
                offset=offset,
            )
        )


@router.patch(
    "/community/questions/{submission_id}/review",
    response_model=CommunityQuestionItem,
)
async def review_community_question(
    submission_id: str,
    payload: CommunityReviewRequest,
    user: dict = Depends(require_admin),
) -> CommunityQuestionItem:
    """M16 approve / reject. Approving mints the bank rows
    (question + options + answer + subject assignment) under
    the shared community document, so the question joins that
    subject's pool at once; rejecting records the reason.
    Reviewing an already-reviewed submission is refused."""
    with _session_or_503() as session:
        return CommunityQuestionItem(
            **community_service.review(
                session,
                user,
                submission_id,
                approved=payload.approved,
                note=payload.note,
            )
        )
