# OfficerPath AI — Phase 2, M5
# Question bank + results reads (GAP-3) and subjects (GAP-4).
#
# All routes require a valid Supabase JWT; every read filters by
# the JWT's user id and answers 404 for unknown or another user's
# questions (never leaks existence). Values come from the engine
# DB only (ADR-011) — no PostgREST, no fake data.
#
# Read-only, except subject assignment (manual, by the owning
# user). Corrections still go through the existing M6 endpoint
# (POST /documents/{id}/questions/{qid}/corrections); this
# router only LISTS the audit trail.

from contextlib import contextmanager

from fastapi import APIRouter, Depends, Query

from app.core.errors import ApiError
from app.db.session import get_session
from app.schemas.questions import (
    AssignSubjectRequest,
    AssignSubjectResponse,
    CorrectionListResponse,
    DocumentQuestionsResponse,
    QuestionDetailResponse,
    QuestionListResponse,
    SubjectListResponse,
)
from app.security.dependencies import get_current_user
from app.services import questions as question_service

router = APIRouter(prefix="/api/v1", tags=["questions"])

MAX_LIST_LIMIT = 100
DEFAULT_BANK_LIMIT = 20
DEFAULT_DOCUMENT_LIMIT = 50


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


@router.get("/questions", response_model=QuestionListResponse)
async def list_questions(
    q: str | None = Query(None, description="Search question text."),
    document_id: str | None = Query(None, description="Only this document's questions."),
    status: str | None = Query(
        None,
        description=f"Answer filter: {', '.join(question_service.BANK_STATUSES)}.",
    ),
    subject_id: str | None = Query(None, description="Only questions assigned this subject."),
    confidence_min: float | None = Query(None, ge=0.0, le=1.0),
    confidence_max: float | None = Query(None, ge=0.0, le=1.0),
    limit: int = Query(DEFAULT_BANK_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
) -> QuestionListResponse:
    with _session_or_503() as session:
        result = question_service.list_questions(
            session,
            user,
            q=q,
            document_id=document_id,
            status=status,
            subject_id=subject_id,
            confidence_min=confidence_min,
            confidence_max=confidence_max,
            limit=limit,
            offset=offset,
        )
    return QuestionListResponse(**result)


@router.get("/questions/{question_id}", response_model=QuestionDetailResponse)
async def get_question(
    question_id: str,
    user: dict = Depends(get_current_user),
) -> QuestionDetailResponse:
    with _session_or_503() as session:
        result = question_service.get_question(session, user, question_id)
    return QuestionDetailResponse(**result)


@router.get("/documents/{document_id}/questions", response_model=DocumentQuestionsResponse)
async def list_document_questions(
    document_id: str,
    limit: int = Query(DEFAULT_DOCUMENT_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
) -> DocumentQuestionsResponse:
    with _session_or_503() as session:
        result = question_service.list_document_questions(
            session, user, document_id, limit=limit, offset=offset
        )
    return DocumentQuestionsResponse(**result)


@router.get(
    "/documents/{document_id}/questions/{question_id}/corrections",
    response_model=CorrectionListResponse,
)
async def list_corrections(
    document_id: str,
    question_id: str,
    user: dict = Depends(get_current_user),
) -> CorrectionListResponse:
    with _session_or_503() as session:
        result = question_service.list_corrections(session, user, document_id, question_id)
    return CorrectionListResponse(**result)


@router.get("/subjects", response_model=SubjectListResponse)
async def list_subjects(
    user: dict = Depends(get_current_user),
) -> SubjectListResponse:
    with _session_or_503() as session:
        result = question_service.list_subjects(session)
    return SubjectListResponse(**result)


@router.post("/questions/{question_id}/subjects", response_model=AssignSubjectResponse)
async def assign_subject(
    question_id: str,
    payload: AssignSubjectRequest,
    user: dict = Depends(get_current_user),
) -> AssignSubjectResponse:
    with _session_or_503() as session:
        result = question_service.assign_subject(
            session, user, question_id, payload.subject_id, payload.topic_id
        )
    return AssignSubjectResponse(**result)


@router.delete("/questions/{question_id}/subjects/{subject_id}")
async def unassign_subject(
    question_id: str,
    subject_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    with _session_or_503() as session:
        return question_service.unassign_subject(session, user, question_id, subject_id)
