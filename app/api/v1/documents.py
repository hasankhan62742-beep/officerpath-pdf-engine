# OfficerPath AI — Phase 2, M4
# Document listing / detail / soft delete (GAP-2).
#
# All routes require a valid Supabase JWT; every read filters by
# the JWT's user id and answers 404 for unknown, deleted, or
# another user's documents (never leaks existence). Values come
# from the engine DB only (ADR-011) — no PostgREST, no fake data.

from contextlib import contextmanager

from fastapi import APIRouter, Depends, Query

from app.config import settings
from app.core.errors import ApiError
from app.database.sqlalchemy_repositories import (
    JOB_STATUSES,
    SqlAlchemyDocumentRepository,
    SqlAlchemyJobRepository,
)
from app.db.session import get_session
from app.schemas.dashboard import (
    DashboardDocumentItem,
    DocumentDeleteResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    JobDetailResponse,
    JobStageItem,
)
from app.schemas.documents import DocumentResponse
from app.security.dependencies import get_current_user
from app.services import documents as document_service
from app.storage.base import StorageBackend
from app.storage.local import LocalDiskStorage

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

MAX_LIST_LIMIT = 100
DEFAULT_LIST_LIMIT = 20


def _storage_backend() -> StorageBackend:
    if settings.storage_backend != "local":
        raise ApiError(
            status_code=503,
            code="storage_unavailable",
            message=f"Storage backend {settings.storage_backend!r} is not configured.",
        )
    return LocalDiskStorage(settings.storage_root)


@contextmanager
def _repositories():
    """Engine-DB repositories for one request (ADR-011). Yields
    (session, documents, jobs); 503 when DATABASE_URL is unset."""
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


def _to_item(item: dict) -> DashboardDocumentItem:
    return DashboardDocumentItem(**item)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    offset: int = Query(0, ge=0),
    status: str | None = Query(
        None, description=f"Filter by job status: {', '.join(JOB_STATUSES)}."
    ),
    user: dict = Depends(get_current_user),
) -> DocumentListResponse:
    with _repositories() as (_, documents, jobs):
        items, total = document_service.list_documents(
            user, documents, jobs, limit=limit, offset=offset, status=status
        )
    return DocumentListResponse(
        documents=[_to_item(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: str,
    user: dict = Depends(get_current_user),
) -> DocumentDetailResponse:
    with _repositories() as (session, documents, jobs):
        detail = document_service.get_document_detail(user, document_id, documents, jobs, session)
    job = detail["job"]
    return DocumentDetailResponse(
        document=DocumentResponse(**detail["document"]),
        job=JobDetailResponse(**job) if job is not None else None,
        stages=[JobStageItem(**s) for s in detail["stages"]],
    )


@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_id: str,
    user: dict = Depends(get_current_user),
) -> DocumentDeleteResponse:
    with _repositories() as (session, documents, jobs):
        result = document_service.delete_document(
            user,
            document_id,
            documents,
            jobs,
            session,
            _storage_backend(),
        )
    return DocumentDeleteResponse(**result)
