# OfficerPath AI — Phase 2, M3 (ADR-011)
# CORS: the browser frontend (http://localhost:3000 by default) may
# call the API with credentials; any other origin gets no CORS
# headers. Never "*" with credentials.

from app.tests.conftest import auth_headers


def test_preflight_from_allowed_origin(client):
    res = client.options(
        "/api/v1/me",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert res.status_code == 200, res.text
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert res.headers.get("access-control-allow-credentials") == "true"


def test_actual_request_from_allowed_origin_gets_cors_headers(client, engine_db):
    res = client.get(
        "/api/v1/me",
        headers={"Origin": "http://localhost:3000", **auth_headers("token-user-a")},
    )
    assert res.status_code in (200, 404)  # 404: no profile yet; CORS still applies
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert res.headers.get("access-control-allow-credentials") == "true"


def test_disallowed_origin_gets_no_cors_headers(client):
    res = client.options(
        "/api/v1/me",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in res.headers


def test_no_wildcard_origin(client):
    res = client.options(
        "/api/v1/me",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.headers.get("access-control-allow-origin") != "*"
