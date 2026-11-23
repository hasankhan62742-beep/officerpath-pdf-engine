# OfficerPath AI — Phase 2, M9
# In-app notifications (GAP-9, doc 03 §2.6). Written by the real
# flows only — upload done/failed + review-needed (worker job
# completion), test submitted / result ready (exam submit). No
# email is ever claimed sent: this table is in-app only.
"""Notification service: create rows from real flows, list and
mark-read for the owning student only. Another user's rows 404
(never leak existence)."""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models as db

NOTIFICATION_TYPES = (
    "upload_done",
    "upload_failed",
    "review_needed",
    "test_submitted",
    "result_ready",
    "subscription_change",
)


def _now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)


def _not_found(what: str = "Not found.") -> ApiError:
    return ApiError(status_code=404, code="not_found", message=what)


def create_notification(
    session: Session,
    user_id: uuid.UUID,
    *,
    type: str,
    title: str,
    body: str,
    link: str | None = None,
) -> db.Notification:
    """Insert one row in the caller's transaction (the caller
    commits). The type CHECK in the table is the last line of
    defence; an unknown type is a 422 here, never a 500."""
    if type not in NOTIFICATION_TYPES:
        raise ApiError(
            status_code=422,
            code="validation_error",
            message=f"Unknown notification type: {type!r}.",
        )
    row = db.Notification(
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        link=link,
    )
    session.add(row)
    return row


def _notification_out(row: db.Notification) -> dict:
    return {
        "id": str(row.id),
        "user_id": str(row.user_id),
        "type": row.type,
        "title": row.title,
        "body": row.body,
        "link": row.link,
        "is_read": bool(row.is_read),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def list_notifications(
    session: Session, user: dict, *, unread_only: bool = False, limit: int = 20, offset: int = 0
) -> dict:
    user_uuid = uuid.UUID(user["id"])
    query = (
        session.query(db.Notification)
        .filter(db.Notification.user_id == user_uuid)
        .order_by(db.Notification.created_at.desc(), db.Notification.id.desc())
    )
    if unread_only:
        query = query.filter(db.Notification.is_read.is_(False))
    total = query.count()
    unread_count = (
        session.query(db.Notification)
        .filter(db.Notification.user_id == user_uuid)
        .filter(db.Notification.is_read.is_(False))
        .count()
    )
    rows = query.limit(limit).offset(offset).all()
    return {
        "items": [_notification_out(row) for row in rows],
        "total": total,
        "unread_count": unread_count,
        "limit": limit,
        "offset": offset,
    }


def mark_read(session: Session, user: dict, notification_id: str) -> dict:
    user_uuid = uuid.UUID(user["id"])
    try:
        row_id = uuid.UUID(notification_id)
    except ValueError:
        raise _not_found("Notification not found.") from None
    row = session.get(db.Notification, row_id)
    if row is None or row.user_id != user_uuid:
        raise _not_found("Notification not found.")
    if not row.is_read:
        row.is_read = True
        session.commit()
    session.refresh(row)
    return _notification_out(row)
