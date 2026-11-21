# OfficerPath AI — PDF Engine (Phase 1A)
# Supabase clients. Two clients, two roles:
#   * ANON client — user-scoped calls (auth verification). Publishable key.
#   * SERVICE-ROLE client — server-side only (job writes, signed URLs).
#     Built ONLY from env vars, never from code, never exposed to clients.
# Both return None when not configured, so /health can report honestly
# instead of crashing at import time.

from functools import lru_cache

from app.config import settings
from app.utils.logging import get_logger
from supabase import Client, create_client

log = get_logger(__name__)


def build_anon_client() -> Client | None:
    if not settings.supabase_configured:
        return None
    return create_client(settings.supabase_url, settings.supabase_anon_key)  # type: ignore[arg-type]


def build_service_client() -> Client | None:
    if not settings.service_role_configured:
        return None
    return create_client(settings.supabase_url, settings.supabase_service_role_key)  # type: ignore[arg-type]


@lru_cache(maxsize=1)
def get_anon_client() -> Client | None:
    try:
        return build_anon_client()
    except Exception:
        log.exception("Failed to create Supabase anon client")
        return None


@lru_cache(maxsize=1)
def get_service_client() -> Client | None:
    try:
        return build_service_client()
    except Exception:
        log.exception("Failed to create Supabase service-role client")
        return None
