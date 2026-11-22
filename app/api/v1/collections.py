# OfficerPath AI — Phase 2, M8
# Question collections (GAP-8): bookmarks, the mistake
# notebook and custom entries — one table, distinguished by
# collection_type. All rows are private per student; another
# user's entries 404 (never leak existence). Bookmarking twice
# is idempotent-200. 'mistake' rows are written by the submit
# flow only, never by this API.

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.api.v1.tests import _session_or_503
from app.schemas.results import (
    CollectionCreateRequest,
    CollectionItem,
    CollectionListResponse,
    CollectionNoteRequest,
)
from app.security.dependencies import get_current_user
from app.services import results as results_service

router = APIRouter(prefix="/api/v1", tags=["collections"])

MAX_LIST_LIMIT = 100
DEFAULT_COLLECTIONS_LIMIT = 20


@router.get("/collections", response_model=CollectionListResponse)
async def list_collections(
    collection_type: str | None = Query(None, description="Filter: bookmark | mistake | custom."),
    limit: int = Query(DEFAULT_COLLECTIONS_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
) -> CollectionListResponse:
    with _session_or_503() as session:
        result = results_service.list_collections(
            session, user, collection_type=collection_type, limit=limit, offset=offset
        )
    return CollectionListResponse(**result)


@router.post("/collections", response_model=CollectionItem)
async def create_collection(
    payload: CollectionCreateRequest,
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    # Idempotent-200: the first bookmark is 201; bookmarking
    # twice returns the existing row with 200 (never 409).
    with _session_or_503() as session:
        result = results_service.create_collection(session, user, payload.model_dump())
    return JSONResponse(
        status_code=200 if result.get("already_exists") else 201,
        content=CollectionItem(**result).model_dump(mode="json"),
    )


@router.patch("/collections/{collection_id}", response_model=CollectionItem)
async def update_collection_note(
    collection_id: str,
    payload: CollectionNoteRequest,
    user: dict = Depends(get_current_user),
) -> CollectionItem:
    with _session_or_503() as session:
        result = results_service.update_collection_note(
            session, user, collection_id, payload.model_dump()
        )
    return CollectionItem(**result)


@router.delete("/collections/{collection_id}")
async def delete_collection(
    collection_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    with _session_or_503() as session:
        return results_service.delete_collection(session, user, collection_id)
