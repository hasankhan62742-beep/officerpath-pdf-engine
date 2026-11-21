# Register endpoint: validation, auth, ownership, idempotency.

from app.tests.conftest import USER_A, USER_B, auth_headers, register_payload


def test_register_success_creates_document_and_job(client):
    res = client.post(
        "/api/v1/documents/register",
        json=register_payload(USER_A),
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["document"]["user_id"] == USER_A
    assert body["document"]["storage_path"] == f"{USER_A}/paper-66.pdf"
    assert body["job"]["document_id"] == body["document"]["id"]
    assert body["job"]["status"] == "queued"
    assert body["job"]["retry_count"] == 0
    assert body["idempotent_replay"] is False


def test_register_requires_auth(client):
    res = client.post("/api/v1/documents/register", json=register_payload(USER_A))
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "unauthorized"


def test_register_rejects_invalid_token(client):
    res = client.post(
        "/api/v1/documents/register",
        json=register_payload(USER_A),
        headers=auth_headers("token-invalid"),
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "invalid_token"


def test_register_validation_errors(client):
    h = auth_headers("token-user-a")
    # bad file type
    res = client.post(
        "/api/v1/documents/register",
        json=register_payload(USER_A, file_type="exe"),
        headers=h,
    )
    assert res.status_code == 422
    # file too large (>100 MB)
    res = client.post(
        "/api/v1/documents/register",
        json=register_payload(USER_A, file_size_bytes=200_000_000),
        headers=h,
    )
    assert res.status_code == 422
    # too many pages (>100)
    res = client.post(
        "/api/v1/documents/register",
        json=register_payload(USER_A, page_count=101),
        headers=h,
    )
    assert res.status_code == 422
    # missing title
    payload = register_payload(USER_A)
    del payload["title"]
    res = client.post("/api/v1/documents/register", json=payload, headers=h)
    assert res.status_code == 422
    # validation errors are structured and leak no internals
    assert "error" in res.json()
    assert "traceback" not in res.text.lower()


def test_register_ownership_other_users_folder_forbidden(client):
    res = client.post(
        "/api/v1/documents/register",
        json=register_payload(USER_B),  # storage path under USER_B
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "forbidden"


def test_register_idempotent_same_key_returns_same_job(client):
    h = auth_headers("token-user-a")
    first = client.post("/api/v1/documents/register", json=register_payload(USER_A), headers=h)
    assert first.status_code == 201
    second = client.post("/api/v1/documents/register", json=register_payload(USER_A), headers=h)
    assert second.status_code == 200
    assert second.json()["idempotent_replay"] is True
    assert second.json()["job"]["id"] == first.json()["job"]["id"]
    assert second.json()["document"]["id"] == first.json()["document"]["id"]


def test_register_idempotent_same_path_no_key_returns_same_job(client):
    h = auth_headers("token-user-a")
    payload = register_payload(USER_A)
    del payload["idempotency_key"]
    first = client.post("/api/v1/documents/register", json=payload, headers=h)
    assert first.status_code == 201
    second = client.post("/api/v1/documents/register", json=payload, headers=h)
    assert second.status_code == 200
    assert second.json()["job"]["id"] == first.json()["job"]["id"]


def test_register_same_key_different_user_is_not_a_replay(client):
    # User A registers with key-1; user B with the same key gets their
    # own job (idempotency is scoped per user).
    res_a = client.post(
        "/api/v1/documents/register",
        json=register_payload(USER_A),
        headers=auth_headers("token-user-a"),
    )
    res_b = client.post(
        "/api/v1/documents/register",
        json=register_payload(USER_B),
        headers=auth_headers("token-user-b"),
    )
    assert res_a.status_code == 201
    assert res_b.status_code == 201
    assert res_a.json()["job"]["id"] != res_b.json()["job"]["id"]
