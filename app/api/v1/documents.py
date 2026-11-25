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
from app.schemas.documents import (
    DocumentResponse,
    ExpectedCountRequest,
    ExpectedCountResponse,
    PageInventoryResponse,
    PageRetryResponse,
)
from app.security.dependencies import get_current_user
from app.security.rate_limit import rate_limiter
from app.services import documents as document_service
from app.services import pages as page_service
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
    include_shared: bool = Query(
        False,
        description="Also list shared bank documents (M11, test builder only).",
    ),
    user: dict = Depends(get_current_user),
) -> DocumentListResponse:
    with _repositories() as (_, documents, jobs):
        items, total = document_service.list_documents(
            user,
            documents,
            jobs,
            limit=limit,
            offset=offset,
            status=status,
            include_shared=include_shared,
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


@router.get("/{document_id}/pages", response_model=PageInventoryResponse)
async def get_document_pages(
    document_id: str,
    user: dict = Depends(get_current_user),
) -> PageInventoryResponse:
    """A3 page inventory: per-page status/counts/errors plus the
    completeness comparison (expected vs extracted, missing
    numbers, zero / low-confidence / failed pages). 404 for
    unknown, deleted, or another user's documents."""
    with _repositories() as (session, documents, jobs):
        document = page_service.require_document_for_user(session, document_id, user["id"])
        return PageInventoryResponse(
            **page_service.get_page_inventory(session, document_id=document.id)
        )


@router.patch("/{document_id}", response_model=ExpectedCountResponse)
async def set_document_expected_count(
    document_id: str,
    body: ExpectedCountRequest,
    user: dict = Depends(get_current_user),
) -> ExpectedCountResponse:
    """A3: store (or clear, with null) the expected question
    count for a document — the owner's statement of how many
    questions the paper holds. Stored in Document.metadata;
    no migration, no re-parse."""
    with _repositories() as (session, documents, jobs):
        document = page_service.require_document_for_user(session, document_id, user["id"])
        return ExpectedCountResponse(
            **page_service.set_expected_question_count(
                session, document=document, expected_count=body.expected_question_count
            )
        )


@router.post(
    "/{document_id}/pages/{page_number}/retry",
    response_model=PageRetryResponse,
    status_code=202,
)
async def retry_document_page(
    document_id: str,
    page_number: int,
    user: dict = Depends(get_current_user),
) -> PageRetryResponse:
    """A3: queue a background job that reprocesses ONE page.
    The worker re-runs the full parse (answer-key detection is
    document-level) and replaces only that page's stored rows —
    every other page's rows keep their ids and corrections. A
    page with manually corrected questions is refused (409);
    a page outside the document is 422."""
    rate_limiter.check(
        f"retry:{user['id']}",
        settings.rate_limit_retry_per_minute,
        settings.rate_limit_window_seconds,
    )
    with _repositories() as (session, documents, jobs):
        document = page_service.require_document_for_user(session, document_id, user["id"])
        return PageRetryResponse(
            **page_service.create_page_retry_job(
                session, document=document, user_id=user["id"], page_number=page_number
            )
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
