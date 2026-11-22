# OfficerPath AI — Phase 2, M3 (GAP-1)
# Student profile endpoints: create/read/update, per-user 404s,
# validation, duplicate-create 409, update-without-profile 404.

from app.tests.conftest import USER_A, USER_B, auth_headers


def _profile_payload(**overrides):
    payload = {
        "full_name": "Muhammad Ahmed",
        "phone": "03001234567",
        "preferred_exam": "PPSC",
        "education_level": "Master's",
    }
    payload.update(overrides)
    return payload


def test_get_me_404_when_no_profile(client, engine_db):
    res = client.get("/api/v1/me", headers=auth_headers("token-user-a"))
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "profile_not_found"


def test_create_then_get_profile_round_trip(client, engine_db):
    res = client.post("/api/v1/me", json=_profile_payload(), headers=auth_headers("token-user-a"))
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["user_id"] == USER_A
    assert body["email"] == f"{USER_A}@example.com"
    assert body["full_name"] == "Muhammad Ahmed"
    assert body["phone"] == "03001234567"
    assert body["preferred_exam"] == "PPSC"
    assert body["education_level"] == "Master's"

    res = client.get("/api/v1/me", headers=auth_headers("token-user-a"))
    assert res.status_code == 200
    assert res.json() == body


def test_create_duplicate_profile_409(client, engine_db):
    h = auth_headers("token-user-a")
    assert client.post("/api/v1/me", json=_profile_payload(), headers=h).status_code == 201
    res = client.post("/api/v1/me", json=_profile_payload(), headers=h)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "profile_exists"


def test_update_profile_round_trip(client, engine_db):
    h = auth_headers("token-user-a")
    assert client.post("/api/v1/me", json=_profile_payload(), headers=h).status_code == 201
    res = client.patch(
        "/api/v1/me",
        json=_profile_payload(full_name="Ahmed Raza", preferred_exam="CSS"),
        headers=h,
    )
    assert res.status_code == 200, res.text
    assert res.json()["full_name"] == "Ahmed Raza"
    assert res.json()["preferred_exam"] == "CSS"
    assert res.json()["phone"] == "03001234567"  # unchanged fields persist

    res = client.get("/api/v1/me", headers=h)
    assert res.json()["full_name"] == "Ahmed Raza"


def test_update_without_profile_404(client, engine_db):
    res = client.patch(
        "/api/v1/me",
        json=_profile_payload(),
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "profile_not_found"


def test_profiles_are_per_user(client, engine_db):
    """User B cannot see or overwrite user A's profile (404 either
    way — never leaks existence)."""
    h_a = auth_headers("token-user-a")
    assert client.post("/api/v1/me", json=_profile_payload(), headers=h_a).status_code == 201
    h_b = auth_headers("token-user-b")
    res = client.get("/api/v1/me", headers=h_b)
    assert res.status_code == 404
    # B creating their own profile works and is separate.
    res = client.post("/api/v1/me", json=_profile_payload(full_name="Bilal Khan"), headers=h_b)
    assert res.status_code == 201
    assert res.json()["user_id"] == USER_B
    assert res.json()["full_name"] == "Bilal Khan"
    # A's profile is untouched.
    assert client.get("/api/v1/me", headers=h_a).json()["full_name"] == "Muhammad Ahmed"


def test_profile_validation_errors(client, engine_db):
    h = auth_headers("token-user-a")
    # empty full name
    res = client.post("/api/v1/me", json=_profile_payload(full_name=""), headers=h)
    assert res.status_code == 422
    # missing full name
    payload = _profile_payload()
    del payload["full_name"]
    res = client.post("/api/v1/me", json=payload, headers=h)
    assert res.status_code == 422
    # optional fields may be omitted entirely
    res = client.post("/api/v1/me", json={"full_name": "Sara"}, headers=h)
    assert res.status_code == 201, res.text
    assert res.json()["phone"] is None
    assert res.json()["preferred_exam"] is None


def test_me_requires_auth(client, engine_db):
    assert client.get("/api/v1/me").status_code == 401
    assert client.post("/api/v1/me", json=_profile_payload()).status_code == 401
    assert client.patch("/api/v1/me", json=_profile_payload()).status_code == 401
