# Security tests: no secret material in any response, error bodies
# never leak internals, and the service-role key is never reachable
# through the API.

import os

from app.tests.conftest import USER_A, auth_headers, register_payload


def test_no_secret_leakage_any_endpoint(client, engine_db, monkeypatch):
    # Plant recognisable fake secret values in the environment and
    # assert none of them ever appears in any response body.
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "SECRET-ROLE-VALUE-12345")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "SECRET-ANON-VALUE-12345")
    h = auth_headers("token-user-a")
    responses = [
        client.get("/health"),
        client.get("/version"),
        client.post(
            "/api/v1/documents/register",
            json=register_payload(USER_A),
            headers=h,
        ),
        client.get("/api/v1/jobs/does-not-exist", headers=h),
        client.post("/api/v1/documents/register", json={"bad": True}, headers=h),
        client.get("/api/v1/jobs/does-not-exist"),
    ]
    for res in responses:
        assert "SECRET-ROLE-VALUE-12345" not in res.text
        assert "SECRET-ANON-VALUE-12345" not in res.text
        assert "sbp_" not in res.text


def test_error_bodies_are_structured_and_generic(client, engine_db):
    res = client.get("/api/v1/jobs/does-not-exist", headers=auth_headers("token-user-a"))
    assert res.status_code == 404
    body = res.json()
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message"}
    assert "traceback" not in res.text.lower()
    assert "Exception" not in res.text


def test_env_example_contains_no_real_secrets():
    # .env.example must contain placeholders only.
    path = os.path.join(os.path.dirname(__file__), "..", "..", ".env.example")
    with open(path) as handle:
        text = handle.read()
    assert "your-anon-key-here" in text
    assert "your-service-role-key-here" in text
    assert "sbp_" not in text
    assert "eyJ" not in text
