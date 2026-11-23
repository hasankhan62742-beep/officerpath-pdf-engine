# OfficerPath AI — PDF Engine (Phase 1A)
# Supabase Auth integration: verify a user's JWT by asking Supabase Auth
# itself (auth.get_user). The token is never decoded locally with a
# hardcoded secret, never logged, and never stored.

from app.core.errors import ApiError
from app.utils.logging import get_logger

log = get_logger(__name__)


def verify_jwt(client, token: str) -> dict:
    """Return {'id': ..., 'email': ..., 'app_metadata': {...}} for a
    valid Supabase JWT.

    ``app_metadata`` is the VERIFIED user record from Supabase Auth
    itself (auth.get_user) — it is the only source of the admin claim
    (M9, doc 05 §4: ``app_metadata.is_admin``). No client request
    body is ever consulted for a role; see ``require_admin``.
    Raises ApiError(401) for missing/invalid/expired tokens and
    ApiError(503) when Auth cannot be reached / is not configured.
    """
    if client is None:
        raise ApiError(
            status_code=503,
            code="auth_unavailable",
            message="Authentication is not configured on this server.",
        )
    try:
        response = client.auth.get_user(token)
    except ApiError:
        raise
    except Exception as err:
        log.exception("Supabase auth verification failed")
        raise ApiError(
            status_code=401,
            code="invalid_token",
            message="Invalid or expired token.",
        ) from err
    user = getattr(response, "user", None)
    if user is None:
        raise ApiError(
            status_code=401,
            code="invalid_token",
            message="Invalid or expired token.",
        )
    user_id = getattr(user, "id", None)
    if not user_id:
        raise ApiError(
            status_code=401,
            code="invalid_token",
            message="Invalid or expired token.",
        )
    app_metadata = getattr(user, "app_metadata", None) or {}
    if not isinstance(app_metadata, dict):
        app_metadata = {}
    return {
        "id": str(user_id),
        "email": getattr(user, "email", None),
        "app_metadata": app_metadata,
    }
