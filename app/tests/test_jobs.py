# Job status + retry tests: ownership (404, never leak), state machine,
# retry counting, rate limiting.

from app.tests.conftest import USER_A, auth_headers, register_payload


def _register(client, user_id, token, **overrides):
    res = client.post(
        "/api/v1/documents/register",
        json=register_payload(user_id, **overrides),
        headers=auth_headers(token),
    )
    assert res.status_code == 201, res.text
    return res.json()["job"]["id"]


def _set_job_status(fake_client, job_id, status):
    for row in fake_client.tables["jobs"]:
        if row["id"] == job_id:
            row["status"] = status
            return


def test_get_job_owner_ok(client):
    job_id = _register(client, USER_A, "token-user-a")
    res = client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers("token-user-a"))
    assert res.status_code == 200
    assert res.json()["id"] == job_id
    assert res.json()["status"] == "queued"


def test_get_job_other_user_404(client):
    job_id = _register(client, USER_A, "token-user-a")
    res = client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers("token-user-b"))
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


def test_get_job_unknown_id_404(client):
    res = client.get(
        "/api/v1/jobs/00000000-0000-0000-0000-000000000000",
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 404


def test_get_job_requires_auth(client):
    job_id = _register(client, USER_A, "token-user-a")
    res = client.get(f"/api/v1/jobs/{job_id}")
    assert res.status_code == 401


def test_retry_only_from_failed_or_cancelled(client, fake_client):
    job_id = _register(client, USER_A, "token-user-a")
    # queued -> 409
    res = client.post(f"/api/v1/jobs/{job_id}/retry", headers=auth_headers("token-user-a"))
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "job_not_retryable"

    # failed -> ok, retry_count 1, status queued
    _set_job_status(fake_client, job_id, "failed")
    res = client.post(f"/api/v1/jobs/{job_id}/retry", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "queued"
    assert res.json()["retry_count"] == 1

    # done -> 409
    _set_job_status(fake_client, job_id, "done")
    res = client.post(f"/api/v1/jobs/{job_id}/retry", headers=auth_headers("token-user-a"))
    assert res.status_code == 409


def test_retry_cancelled_allowed(client, fake_client):
    job_id = _register(client, USER_A, "token-user-a")
    _set_job_status(fake_client, job_id, "cancelled")
    res = client.post(f"/api/v1/jobs/{job_id}/retry", headers=auth_headers("token-user-a"))
    assert res.status_code == 200
    assert res.json()["retry_count"] == 1


def test_retry_other_user_404(client):
    job_id = _register(client, USER_A, "token-user-a")
    res = client.post(f"/api/v1/jobs/{job_id}/retry", headers=auth_headers("token-user-b"))
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


def test_retry_rate_limited(client, fake_client):
    # 5 retries/minute per user; the 6th retry attempt is rate-limited.
    # Each retry needs the job back in a retryable state.
    job_id = _register(client, USER_A, "token-user-a")
    h = auth_headers("token-user-a")
    for _ in range(5):
        _set_job_status(fake_client, job_id, "failed")
        res = client.post(f"/api/v1/jobs/{job_id}/retry", headers=h)
        assert res.status_code == 200, res.text
    _set_job_status(fake_client, job_id, "failed")
    res = client.post(f"/api/v1/jobs/{job_id}/retry", headers=h)
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "rate_limited"
