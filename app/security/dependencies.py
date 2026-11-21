# OfficerPath AI — PDF Engine (Phase 1A)
# Auth dependency for protected routes. The Supabase client used here is
# the one attached to app.state at startup (overridable in tests).

from fastapi import Header, Request

from app.core.errors import ApiError
from app.integrations.supabase_auth import verify_jwt


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
