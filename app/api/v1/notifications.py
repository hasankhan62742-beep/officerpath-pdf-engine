# OfficerPath AI — Phase 2, M9
# In-app notifications API (GAP-9, doc 03 §2.6). Owner-only,
# newest first. In-app ONLY — no email is ever claimed sent.
# Mark-read is PATCH /{id}/read (idempotent: reading a read
# row returns the same row).

from fastapi import APIRouter, Depends, Query

from app.api.v1.tests import _session_or_503
from app.schemas.notifications import NotificationItem, NotificationListResponse
from app.security.dependencies import get_current_user
from app.services import notifications as notifications_service

router = APIRouter(prefix="/api/v1", tags=["notifications"])

MAX_LIST_LIMIT = 100
DEFAULT_LIMIT = 20


@router.get("/notifications", response_model=NotificationListResponse)
async def list_notifications(
    unread_only: bool = Query(False, description="Only unread rows."),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
) -> NotificationListResponse:
    with _session_or_503() as session:
        return NotificationListResponse(
            **notifications_service.list_notifications(
                session, user, unread_only=unread_only, limit=limit, offset=offset
            )
        )


@router.patch("/notifications/{notification_id}/read", response_model=NotificationItem)
async def mark_notification_read(
    notification_id: str,
    user: dict = Depends(get_current_user),
) -> NotificationItem:
    with _session_or_503() as session:
        return NotificationItem(**notifications_service.mark_read(session, user, notification_id))
