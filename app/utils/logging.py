# OfficerPath AI — PDF Engine (Phase 1A)
# Structured JSON logging. Never log secrets, tokens, or key material:
# Authorization headers and any value whose key looks like a secret are
# redacted before the record is emitted.

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

_SECRET_KEY_RE = re.compile(r"(key|token|secret|password|auth|bearer)", re.I)


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: ("***REDACTED***" if _SECRET_KEY_RE.search(str(k)) else _redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return [_redact(v) for v in obj]
    if isinstance(obj, str) and obj.lower().startswith("bearer "):
        return "Bearer ***REDACTED***"
    return obj


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update(_redact(extra))
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_fields(**fields: Any) -> dict[str, Any]:
    """Attach structured fields to a log record, e.g. log_fields(job_id=...)."""
    return {"fields": fields}
