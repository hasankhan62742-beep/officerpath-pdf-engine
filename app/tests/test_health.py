# Health + version endpoint tests.


def test_health_ok_with_configured_supabase(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] in ("ok", "degraded")
    assert body["checks"]["supabase"] == "ok"
    assert body["service"] == "officerpath-pdf-engine"
    assert "version" in body and "environment" in body


def test_health_no_secret_material(client):
    res = client.get("/health")
    body = res.text
    # No key material may ever appear in a response body.
    for forbidden in ("service_role", "sbp_", "SUPABASE_SERVICE_ROLE_KEY"):
        assert forbidden not in body


def test_version_returns_version_and_environment(client):
    res = client.get("/version")
    assert res.status_code == 200
    body = res.json()
    assert body["service"] == "officerpath-pdf-engine"
    assert body["version"] == "0.1.0"
    assert body["environment"]
    # git_commit is None when no git repo is present (this VM); either
    # a short hash or null is acceptable — never an error.
    assert body["git_commit"] is None or isinstance(body["git_commit"], str)
