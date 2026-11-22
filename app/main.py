# OfficerPath AI — PDF Engine (Phase 1A)
# FastAPI application entrypoint. Run locally with:
#   uvicorn app.main:app --reload --port 8000
# In production Render starts it via the Dockerfile CMD (ADR-001).
# Uvicorn handles SIGTERM gracefully (in-flight requests finish);
# see README "Graceful shutdown".

import asyncio
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import health as health_api
from app.api import metrics as metrics_api
from app.api.v1 import async_jobs as async_jobs_routes
from app.api.v1 import dashboard as dashboard_routes
from app.api.v1 import documents as documents_routes
from app.api.v1 import me as me_routes
from app.api.v1 import questions as questions_routes
from app.api.v1 import review as review_routes
from app.api.v1 import routes as v1_routes
from app.api.v1 import tests as tests_routes
from app.config import settings
from app.core.errors import (
    ApiError,
    api_error_handler,
    error_body,
    unhandled_error_handler,
)
from app.database.supabase_client import get_anon_client, get_service_client
from app.utils import metrics
from app.utils.logging import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)


def _run_worker_forever() -> None:
    """The in-process worker loop (runs in a thread, never on the
    event loop — process_job is synchronous and CPU-heavy). Only
    started when WORKER_ENABLED=true (ADR-009)."""
    from sqlalchemy.orm import sessionmaker

    from app.db.session import get_engine
    from app.workers.runner import run_forever

    engine = get_engine()
    if engine is None:
        log.info("worker not started: DATABASE_URL is not configured")
        return
    run_forever(sessionmaker(bind=engine))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Clients are built once at startup. Either may be None when the
    # corresponding env vars are absent; endpoints report that honestly
    # (503) instead of crashing.
    app.state.supabase_client = get_anon_client()
    app.state.service_client = get_service_client()
    log.info(
        "officerpath-pdf-engine starting",
        extra={
            "fields": {
                "version": settings.app_version,
                "environment": settings.environment,
                "supabase_configured": settings.supabase_configured,
                "service_role_configured": settings.service_role_configured,
                "worker_enabled": settings.worker_enabled,
            }
        },
    )
    worker_task = None
    if settings.worker_enabled:
        # In-process worker (ADR-009): one background task polling
        # the job table. Disabled by default — the API serves
        # without it, and tests never start it.
        worker_task = asyncio.create_task(asyncio.to_thread(_run_worker_forever))
    yield
    if worker_task is not None:
        worker_task.cancel()
    log.info("officerpath-pdf-engine shutting down")


app = FastAPI(
    title="OfficerPath PDF Engine",
    version=settings.app_version,
    description=(
        "Server-side document intelligence engine for OfficerPath AI. "
        "Phase 1 M1: register/upload/ingestion + schema. "
        "No OCR or parsing yet — that is M2–M5."
    ),
    lifespan=lifespan,
)


@app.middleware("http")
async def request_id_and_logging(request: Request, call_next):
    request_id = str(uuid.uuid4())
    # Stash on request.state so routes can reuse it as the pipeline
    # correlation id (ingestion stage history, logs).
    request.state.request_id = request_id
    started = time.monotonic()
    response = await call_next(request)
    duration_ms = round((time.monotonic() - started) * 1000, 1)
    response.headers["X-Request-Id"] = request_id
    # M7 observability: every request is one structured JSON log
    # line (method, path, status, duration) + one metrics sample.
    # The path is the URL path only — never a query string (it could
    # carry ids) and never a body.
    metrics.inc("http_requests_total", {"status": str(response.status_code)})
    log.info(
        "request",
        extra={
            "fields": {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            }
        },
    )
    return response


@app.exception_handler(ApiError)
async def _api_error_handler(request: Request, exc: ApiError):
    metrics.inc("errors_total", {"code": exc.code})
    return api_error_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError):
    # Pydantic validation failures: structured, no internal detail.
    metrics.inc("errors_total", {"code": "validation_error"})
    return JSONResponse(
        status_code=422,
        content=error_body("validation_error", "The request body failed validation."),
    )


@app.exception_handler(Exception)
async def _unhandled_error_handler(request: Request, exc: Exception):
    metrics.inc("errors_total", {"code": "unhandled"})
    return unhandled_error_handler(request, exc)


@app.middleware("http")
async def request_size_limit(request: Request, call_next):
    """M7 security: reject oversize request bodies at the API layer
    (422, code file_too_large — the same status and code the M1
    ingestion validator returns, so one oversize shape holds across
    every endpoint) before any route reads them into memory. The
    limit is the same max_file_size_bytes the ingestion validator
    enforces per file — a body larger than that can never be a valid
    upload. Requests without a Content-Length (chunked) are checked
    by the route handlers after reading (len(data) > limit -> 422)."""
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > settings.max_file_size_bytes:
                return JSONResponse(
                    status_code=422,
                    content=error_body(
                        "file_too_large",
                        f"Request body is {content_length} bytes; "
                        f"limit is {settings.max_file_size_bytes}.",
                    ),
                )
        except ValueError:
            pass
    return await call_next(request)


app.include_router(health_api.router)
app.include_router(metrics_api.router)
app.include_router(v1_routes.router)
app.include_router(review_routes.router)
app.include_router(async_jobs_routes.router)
app.include_router(me_routes.router)
app.include_router(documents_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(questions_routes.router)
app.include_router(tests_routes.router)

# CORS (M3, ADR-011): the browser frontend calls this API. Origins
# come from CORS_ALLOWED_ORIGINS (dev default http://localhost:3000);
# credentials are allowed only with an explicit origin list — never
# "*". Added after the routers so the request-id / size-limit
# middlewares still run on cross-origin requests; preflight OPTIONS
# is answered here before any route reads a body.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
