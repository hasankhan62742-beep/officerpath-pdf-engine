# OfficerPath AI — Phase 1, M7
# Observability: /health reports real dependency state, /metrics
# returns real numbers from a run, every request is one structured
# JSON log line with a duration. No log or metric ever carries file
# contents, OCR text, or secrets.

import logging
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.metrics as metrics_api
import app.api.v1.async_jobs as async_jobs_api
from app.config import settings
from app.db.models import Base
from app.db.session import reset_engine_for_tests
from app.tests.conftest import USER_A, auth_headers
from app.utils import metrics

FIX = __import__("pathlib").Path(__file__).resolve().parent / "fixtures/golden/ppsc66"
CA40 = FIX / "ppsc-current-affairs-40-mcqs.pdf"


def test_health_reports_real_dependency_state(client) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    checks = res.json()["checks"]
    # Supabase: the fake client answers (test env).
    assert checks["supabase"] == "ok"
    # No DATABASE_URL in tests: honestly not_configured.
    assert checks["database"] == "not_configured"
    # Tesseract is installed on this VM; PaddleOCR is a string,
    # never faked as available when it is not.
    assert checks["ocr_tesseract"] == "available"
    assert checks["ocr_paddleocr"] in (
        "available",
        "unavailable",
        "disabled",
        "disabled_on_render_free",
    )
    assert checks["disk"] == "ok"
    assert res.json()["status"] in ("ok", "degraded")


def test_health_database_unreachable_is_503(client, monkeypatch) -> None:
    # A configured-but-dead database must be a 503, not a fake ok.
    reset_engine_for_tests()
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://bad:bad@127.0.0.1:1/db")
    try:
        res = client.get("/health")
        assert res.status_code == 503
        assert res.json()["checks"]["database"] == "unreachable"
    finally:
        reset_engine_for_tests()


def test_metrics_returns_real_numbers_after_a_parse(client) -> None:
    metrics.reset()
    with CA40.open("rb") as fh:
        res = client.post(
            "/api/v1/documents/parse",
            files={"file": ("ca40.pdf", fh, "application/pdf")},
            headers=auth_headers("token-user-a"),
        )
    assert res.status_code == 200
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "text/plain" in res.headers["content-type"]
    text = res.text
    assert 'documents_parsed_total{engine="digital"} 1' in text
    assert 'ocr_calls_total{engine="digital"} 1' in text
    assert "http_requests_total" in text
    # No database in this test: no jobs gauge (never faked).
    assert "officerpath_jobs_current" not in text
    # No user data in metrics, ever.
    assert USER_A not in text
    assert "ca40" not in text


def test_metrics_jobs_gauge_with_database(client, tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path}/metrics.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(async_jobs_api, "get_session", lambda: factory())
    monkeypatch.setattr(metrics_api, "get_session", lambda: factory())
    monkeypatch.setattr(settings, "storage_root", str(tmp_path / "storage"))
    metrics.reset()
    with CA40.open("rb") as fh:
        res = client.post(
            "/api/v1/async-jobs/parse",
            files={"file": ("ca40.pdf", fh, "application/pdf")},
            headers=auth_headers("token-user-a"),
        )
    assert res.status_code == 202
    text = client.get("/metrics").text
    assert 'officerpath_jobs_current{status="queued"} 1' in text
    engine.dispose()


def test_request_log_line_has_duration_ms(client, caplog) -> None:
    with caplog.at_level(logging.INFO, logger="app.main"):
        res = client.get("/health")
    assert res.status_code == 200
    records = [
        r
        for r in caplog.records
        if getattr(r, "fields", {}).get("message") == "request" or r.getMessage() == "request"
    ]
    assert records, "no request log line emitted"
    fields = getattr(records[-1], "fields", {})
    assert "duration_ms" in fields
    assert fields["method"] == "GET"
    assert fields["path"] == "/health"
    assert fields["status_code"] == 200
    # The log line carries no query string and no body.
    assert "token" not in str(fields).lower()


def test_json_log_formatter_redacts_secret_keys() -> None:
    from app.utils.logging import JsonFormatter

    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="x.py",
        lineno=1,
        msg="hi",
        args=(),
        exc_info=None,
    )
    record.fields = {"api_key": "sk-live-123", "job_id": str(uuid.uuid4())}
    line = formatter.format(record)
    assert "sk-live-123" not in line
    assert "***REDACTED***" in line
    assert "job_id" in line
