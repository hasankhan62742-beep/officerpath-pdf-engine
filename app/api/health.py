# OfficerPath AI — PDF Engine (Phase 1A)
# Operational endpoints. No secrets are ever included in these responses.

import importlib.util
import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter, Request

from app.config import settings
from app.db.session import get_engine
from app.schemas.documents import HealthResponse, VersionResponse
from app.utils.logging import get_logger

log = get_logger(__name__)
router = APIRouter()

#: Disk space below this is reported as low (uploads may still work
#: for small files — degraded, not down).
DISK_LOW_FREE_MB = 100


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


def _check_database() -> str:
    """SQLAlchemy database (the engine-owned tables): ok when a
    connection answers, unreachable when configured but down,
    not_configured when DATABASE_URL is unset."""
    if not settings.database_configured:
        return "not_configured"
    engine = get_engine()
    if engine is None:
        return "unreachable"
    try:
        from sqlalchemy import text

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "unreachable"


def _check_ocr() -> dict[str, str]:
    """OCR engine availability (cheap probes, no model loads):
    Tesseract = binary on PATH; PaddleOCR = package importable AND
    enabled AND allowed on this deployment profile (ADR-005/006 —
    it cannot run on Render free)."""
    checks = {}
    checks["tesseract"] = "available" if shutil.which(settings.tesseract_binary) else "unavailable"
    paddle_spec = importlib.util.find_spec("paddleocr")
    if not settings.paddleocr_enabled:
        checks["paddleocr"] = "disabled"
    elif paddle_spec is None:
        checks["paddleocr"] = "unavailable"
    elif settings.deployment_profile == "render-free":
        checks["paddleocr"] = "disabled_on_render_free"
    else:
        checks["paddleocr"] = "available"
    return checks


def _check_disk() -> str:
    """Free space under the storage root (Render's filesystem is
    ephemeral; uploads need headroom)."""
    root = Path(settings.storage_root)
    path = root if root.exists() else Path(".")
    try:
        free_mb = shutil.disk_usage(path).free / (1024 * 1024)
    except Exception:
        return "unavailable"
    return "ok" if free_mb >= DISK_LOW_FREE_MB else "low"


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """App health. 200 when healthy; 503 when a CONFIGURED dependency
    (Supabase, database) is unreachable. Unconfigured dependencies
    report 'not_configured' and the app is degraded (200), never
    faking 'ok'. OCR engines and disk space are reported honestly
    too — a missing Tesseract is degraded, never hidden."""
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
    database = _check_database()
    checks["database"] = database
    if database == "unreachable":
        status = "degraded"
        http_status = 503
    elif database == "not_configured" and status == "ok":
        status = "degraded"
    ocr = _check_ocr()
    checks.update({f"ocr_{k}": v for k, v in ocr.items()})
    if ocr["tesseract"] != "available" and status == "ok":
        # Scanned pages cannot be OCR'd without Tesseract — the
        # app still serves digital PDFs, so degraded, not down.
        status = "degraded"
    disk = _check_disk()
    checks["disk"] = disk
    if disk != "ok" and status == "ok":
        status = "degraded"
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
