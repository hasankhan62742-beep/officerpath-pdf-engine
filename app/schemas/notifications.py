# OfficerPath AI — Phase 2, M9
# Notification schemas (GAP-9, doc 03 §2.6). In-app only.

from pydantic import BaseModel, Field


class NotificationItem(BaseModel):
    id: str
    user_id: str
    type: str
    title: str
    body: str
    link: str | None = None
    is_read: bool
    created_at: str | None = None


class NotificationListResponse(BaseModel):
    items: list[NotificationItem]
    total: int
    unread_count: int
    limit: int = Field(default=20)
    offset: int = Field(default=0)
