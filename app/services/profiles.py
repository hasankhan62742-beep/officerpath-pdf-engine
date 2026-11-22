# OfficerPath AI — PDF Engine (Phase 2, M3)
# Student profile service (GAP-1, doc 03 §2.1): one profile row per
# Supabase Auth user in the engine DB.
#
# Ownership: every query filters by the JWT's user id. A user reads
# or writes only their own profile; another user's profile is 404
# (never leaks existence) — the Phase 1 pattern. The user_id is
# never accepted from a request body.

import uuid

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models as db


def _row(profile: db.StudentProfile, email: str | None) -> dict:
    return {
        "user_id": str(profile.user_id),
        "email": email,
        "full_name": profile.full_name,
        "phone": profile.phone,
        "preferred_exam": profile.preferred_exam,
        "education_level": profile.education_level,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


def get_profile(session: Session, *, user_id: str, email: str | None) -> dict:
    """Own profile, or 404 (no profile row yet — the client shows
    the creation form)."""
    profile = (
        session.query(db.StudentProfile)
        .filter(db.StudentProfile.user_id == uuid.UUID(user_id))
        .first()
    )
    if profile is None:
        raise ApiError(
            status_code=404,
            code="profile_not_found",
            message="No profile exists for this user yet.",
        )
    return _row(profile, email)


def create_profile(session: Session, *, user_id: str, email: str | None, data: dict) -> dict:
    """Create the profile. 409 when one already exists (use PATCH to
    update). The unique constraint on user_id is the backstop; the
    read-then-write check is the friendly path."""
    existing = (
        session.query(db.StudentProfile)
        .filter(db.StudentProfile.user_id == uuid.UUID(user_id))
        .first()
    )
    if existing is not None:
        raise ApiError(
            status_code=409,
            code="profile_exists",
            message="A profile already exists for this user.",
        )
    profile = db.StudentProfile(
        user_id=uuid.UUID(user_id),
        full_name=data["full_name"],
        phone=data.get("phone"),
        preferred_exam=data.get("preferred_exam"),
        education_level=data.get("education_level"),
    )
    session.add(profile)
    session.commit()
    return _row(profile, email)


def update_profile(session: Session, *, user_id: str, email: str | None, data: dict) -> dict:
    """Update the profile. 404 when none exists (use POST to create).
    Only the fields the client sent are changed."""
    profile = (
        session.query(db.StudentProfile)
        .filter(db.StudentProfile.user_id == uuid.UUID(user_id))
        .first()
    )
    if profile is None:
        raise ApiError(
            status_code=404,
            code="profile_not_found",
            message="No profile exists for this user yet.",
        )
    profile.full_name = data["full_name"]
    profile.phone = data.get("phone")
    profile.preferred_exam = data.get("preferred_exam")
    profile.education_level = data.get("education_level")
    session.commit()
    return _row(profile, email)
