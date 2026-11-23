# OfficerPath AI — PDF Engine (Phase 1A)
# Auth dependency for protected routes. The Supabase client used here is
# the one attached to app.state at startup (overridable in tests).

from fastapi import Depends, Header, Request

from app.core.errors import ApiError
from app.integrations.supabase_auth import verify_jwt
from app.utils.logging import get_logger

log = get_logger(__name__)


def get_anon_client_from_state(request: Request):
    return getattr(request.app.state, "supabase_client", None)


def get_service_client_from_state(request: Request):
    return getattr(request.app.state, "service_client", None)


async def get_current_user(
    request: Request, authorization: str | None = Header(default=None)
) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(
            status_code=401,
            code="unauthorized",
            message="A valid Bearer token is required.",
        )
    token = authorization[7:].strip()
    if not token:
        raise ApiError(
            status_code=401,
            code="unauthorized",
            message="A valid Bearer token is required.",
        )
    client = get_anon_client_from_state(request)
    return verify_jwt(client, token)


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Admin gate (M9, doc 05 §4). The admin claim comes ONLY from
    the verified Supabase JWT user record
    (``app_metadata.is_admin``) — set by the owner via the Supabase
    Dashboard / service-role script, never self-assigned, never
    settable through any API. No request body is consulted.

    Non-admins get 404 (same no-leak pattern as every other owner
    check: a 403 would confirm the route exists). Denied attempts
    are logged (user id only, never a token) for the admin-visible
    audit trail.
    """
    app_metadata = user.get("app_metadata") or {}
    if isinstance(app_metadata, dict) and app_metadata.get("is_admin") is True:
        return user
    log.warning(
        "admin route denied for non-admin user",
        extra={"fields": {"user_id": user.get("id")}},
    )
    raise ApiError(
        status_code=404,
        code="not_found",
        message="Not found.",
    )
