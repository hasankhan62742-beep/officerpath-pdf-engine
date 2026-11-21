# OfficerPath AI — PDF Engine (Phase 1A)
# FastAPI application entrypoint. Run locally with:
#   uvicorn app.main:app --reload --port 8000
# In production Render starts it via the Dockerfile CMD (ADR-001).
# Uvicorn handles SIGTERM gracefully (in-flight requests finish);
# see README "Graceful shutdown".

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import health as health_api
from app.api.v1 import routes as v1_routes
from app.config import settings
from app.core.errors import (
    ApiError,
    api_error_handler,
    error_body,
    unhandled_error_handler,
)
from app.database.supabase_client import get_anon_client, get_service_client
from app.utils.logging import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)


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
            }
        },
    )
    yield
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
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    log.info(
        "request",
        extra={
            "fields": {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
            }
        },
    )
    return response


@app.exception_handler(ApiError)
async def _api_error_handler(request: Request, exc: ApiError):
    return api_error_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError):
    # Pydantic validation failures: structured, no internal detail.
    return JSONResponse(
        status_code=422,
        content=error_body("validation_error", "The request body failed validation."),
    )


@app.exception_handler(Exception)
async def _unhandled_error_handler(request: Request, exc: Exception):
    return unhandled_error_handler(request, exc)


app.include_router(health_api.router)
app.include_router(v1_routes.router)
