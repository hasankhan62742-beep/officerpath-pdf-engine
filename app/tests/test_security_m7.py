# OfficerPath AI — Phase 1, M7
# Security: every protected route requires auth, per-user scoping
# holds on the new async-jobs routes, bad input never becomes a
# 500, oversize bodies are rejected at the API layer (422, code
# file_too_large — the M1 upload contract), the parse endpoints
# anywhere in the shipped code.

import re
import subprocess
from pathlib import Path

from app.tests.conftest import USER_A, auth_headers, register_payload

REPO = Path(__file__).resolve().parent.parent.parent


def test_every_protected_route_requires_auth(client) -> None:
    unauthenticated = [
        ("get", "/api/v1/jobs/does-not-exist", None),
        ("post", "/api/v1/jobs/does-not-exist/retry", None),
        ("post", "/api/v1/documents/register", {"json": register_payload(USER_A)}),
        (
            "post",
            "/api/v1/documents/upload",
            {"files": {"file": ("a.pdf", b"%PDF", "application/pdf")}},
        ),
        (
            "post",
            "/api/v1/documents/upload/batch",
            {"files": [("files", ("a.pdf", b"%PDF", "application/pdf"))]},
        ),
        (
            "post",
            "/api/v1/documents/parse",
            {"files": {"file": ("a.pdf", b"%PDF", "application/pdf")}},
        ),
        (
            "post",
            "/api/v1/documents/parse-image",
            {"files": {"file": ("a.png", b"\x89PNG", "image/png")}},
        ),
        ("get", "/api/v1/jobs/does-not-exist/review", None),
        (
            "post",
            "/api/v1/documents/does-not-exist/questions/x/corrections",
            {"json": {"field": "answer", "new_value": "B"}},
        ),
        ("get", "/api/v1/documents/does-not-exist/report", None),
        (
            "post",
            "/api/v1/async-jobs/parse",
            {"files": {"file": ("a.pdf", b"%PDF", "application/pdf")}},
        ),
        ("get", "/api/v1/async-jobs/does-not-exist", None),
        ("post", "/api/v1/async-jobs/does-not-exist/cancel", None),
        ("post", "/api/v1/async-jobs/does-not-exist/retry", None),
    ]
    for method, path, kwargs in unauthenticated:
        res = getattr(client, method)(path, **(kwargs or {}))
        assert res.status_code == 401, (method, path, res.status_code, res.text)


def test_public_endpoints_need_no_auth(client) -> None:
    for path in ("/health", "/version", "/metrics"):
        res = client.get(path)
        assert res.status_code == 200, (path, res.status_code)


def test_bad_input_never_becomes_500(client) -> None:
    h = auth_headers("token-user-a")
    cases = [
        ("get", "/api/v1/jobs/not-a-uuid", None),
        ("get", "/api/v1/jobs/11111111-1111-1111-1111-111111111111/review", None),
        ("get", "/api/v1/documents/11111111-1111-1111-1111-111111111111/report", None),
        ("post", "/api/v1/documents/register", {"json": {"bad": True}}),
        ("post", "/api/v1/documents/register", {"json": register_payload("not-a-uuid")}),
        (
            "post",
            "/api/v1/documents/upload",
            {"files": {"file": ("empty.pdf", b"", "application/pdf")}},
        ),
        ("get", "/api/v1/async-jobs/not-a-uuid", None),
        ("post", "/api/v1/async-jobs/not-a-uuid/cancel", None),
        ("post", "/api/v1/async-jobs/not-a-uuid/retry", None),
    ]
    for method, path, kwargs in cases:
        res = getattr(client, method)(path, headers=h, **(kwargs or {}))
        assert res.status_code != 500, (method, path, res.text)
        assert res.status_code in (401, 403, 404, 409, 422, 429, 503), (
            method,
            path,
            res.status_code,
        )


def test_oversize_body_rejected_422_before_reading(client, monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "max_file_size_bytes", 1024)
    res = client.post(
        "/api/v1/documents/parse",
        files={"file": ("big.pdf", b"%PDF" + b"0" * 2048, "application/pdf")},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "file_too_large"


def test_parse_image_rate_limited(client) -> None:
    # The rate limit is checked BEFORE the file is validated, so
    # 11 invalid uploads cost no OCR: the first 10 are 422, the
    # 11th is 429.
    h = auth_headers("token-user-a")
    statuses = []
    for _ in range(11):
        res = client.post(
            "/api/v1/documents/parse-image",
            files={"file": ("x.txt", b"hello", "text/plain")},
            headers=h,
        )
        statuses.append(res.status_code)
    assert statuses[:10] == [422] * 10
    assert statuses[10] == 429


def test_no_hardcoded_secrets_in_shipped_code() -> None:
    # Method: scan every shipped .py file (app/, excluding tests)
    # for an assignment of a string literal to a secret-looking
    # name. Settings read secrets from env only (values are None
    # by default); tests use fake tokens, which live in tests/.
    pattern = re.compile(
        r"""(?i)(api[_-]?key|secret|password|bearer|supabase[_-]?service[_-]?role[_-]?key)\s*[:=]\s*["'][A-Za-z0-9_\-./]{8,}["']"""
    )
    offenders = []
    for path in sorted((REPO / "app").rglob("*.py")):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(REPO)}:{lineno}: {line.strip()}")
    assert offenders == [], offenders


def test_no_env_file_tracked() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, cwd=REPO
    ).stdout.splitlines()
    assert ".env" not in tracked
    assert not [t for t in tracked if t.endswith(".env")]
