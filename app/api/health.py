# OfficerPath AI — PDF Engine (Phase 1A)
# Operational endpoints. No secrets are ever included in these responses.

import subprocess

from fastapi import APIRouter, Request

from app.config import settings
from app.schemas.documents import HealthResponse, VersionResponse
from app.utils.logging import get_logger

log = get_logger(__name__)
router = APIRouter()


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """App health. 200 when healthy; 503 when a CONFIGURED dependency
    (Supabase) is unreachable. Supabase is only checked when configured:
    without SUPABASE_URL/ANON key the check reports 'not_configured'
    and the app itself is still healthy."""
    from fastapi.responses import JSONResponse

    checks: dict[str, str] = {"config": "ok"}
    supabase_client = getattr(request.app.state, "supabase_client", None)
    if not settings.supabase_configured:
        checks["supabase"] = "not_configured"
        status = "degraded"
        http_status = 200
    else:
        try:
            supabase_client.table("documents").select("id").limit(1).execute()
            checks["supabase"] = "ok"
            status = "ok"
            http_status = 200
        except Exception:
            checks["supabase"] = "unreachable"
            status = "degraded"
            http_status = 503
    body = HealthResponse(
        status=status,
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        checks=checks,
    )
    return JSONResponse(status_code=http_status, content=body.model_dump())


@router.get("/version", response_model=VersionResponse)
async def version() -> VersionResponse:
    return VersionResponse(
        service=settings.app_name,
        version=settings.app_version,
        git_commit=_git_commit(),
        environment=settings.environment,
    )
