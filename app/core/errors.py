# OfficerPath AI — PDF Engine (Phase 1A)
# Error model: every API error is a structured JSON body with a stable
# machine-readable code and a user-facing message. Internal details
# (stack traces, DB errors, key material) are NEVER returned to clients.

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """Application error with a public code/message and an HTTP status."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message))


def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Deliberately generic: no exception text, no traceback in the response.
    return JSONResponse(
        status_code=500,
        content=error_body("internal_error", "An unexpected error occurred."),
    )
