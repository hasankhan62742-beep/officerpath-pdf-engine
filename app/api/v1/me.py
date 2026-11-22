# OfficerPath AI — PDF Engine (Phase 2, M3)
# Student profile endpoints (GAP-1, doc 03 §2.1).
#
# GET /api/v1/me — own profile (404 profile_not_found when none).
# POST /api/v1/me — create (201; 409 profile_exists when one exists).
# PATCH /api/v1/me — update (404 when none exists; use POST first).
#
# Auth: Supabase JWT via get_current_user (same dependency as every
# other /api/v1 endpoint). The user_id comes from the JWT only.
# Rate-limited: 10 profile writes/user/minute (doc 05 §1 pattern).

from fastapi import APIRouter, Depends

from app.config import settings
from app.core.errors import ApiError
from app.db.session import get_session
from app.schemas.me import ProfileIn, ProfileResponse
from app.security.dependencies import get_current_user
from app.security.rate_limit import rate_limiter
from app.services import profiles as profile_service

router = APIRouter(prefix="/api/v1/me", tags=["me"])


def _session_or_503():
    session = get_session()
    if session is None:
        raise ApiError(
            status_code=503,
            code="database_unavailable",
            message="The database is not configured on this server.",
        )
    return session


def _rate_limit_write(user_id: str) -> None:
    rate_limiter.check(
        f"profile:{user_id}",
        settings.rate_limit_register_per_minute,
        settings.rate_limit_window_seconds,
    )


@router.get("", response_model=ProfileResponse)
def get_me(user: dict = Depends(get_current_user)) -> ProfileResponse:
    session = _session_or_503()
    try:
        return ProfileResponse(
            **profile_service.get_profile(session, user_id=user["id"], email=user.get("email"))
        )
    finally:
        session.close()


@router.post("", response_model=ProfileResponse, status_code=201)
def create_me(
    payload: ProfileIn,
    user: dict = Depends(get_current_user),
) -> ProfileResponse:
    _rate_limit_write(user["id"])
    session = _session_or_503()
    try:
        return ProfileResponse(
            **profile_service.create_profile(
                session,
                user_id=user["id"],
                email=user.get("email"),
                data=payload.model_dump(),
            )
        )
    finally:
        session.close()


@router.patch("", response_model=ProfileResponse)
def update_me(
    payload: ProfileIn,
    user: dict = Depends(get_current_user),
) -> ProfileResponse:
    _rate_limit_write(user["id"])
    session = _session_or_503()
    try:
        return ProfileResponse(
            **profile_service.update_profile(
                session,
                user_id=user["id"],
                email=user.get("email"),
                data=payload.model_dump(),
            )
        )
    finally:
        session.close()
