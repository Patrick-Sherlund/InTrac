import time

import pytest
from fastapi.testclient import TestClient

from app.main import SESSION_COOKIE, create_app
from app.storage import connect, hash_password, hash_token, insert_user, verify_password


PASSWORD = "test-password-for-intrac"
NEW_USER = {"first_name": "Taylor", "last_name": "Morgan", "username": "tmorgan", "password": PASSWORD}


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / "intrac.db"
    with TestClient(create_app(path)) as client:
        insert_user(path, first_name="System", last_name="Admin", username="admin", password=PASSWORD, role="ADMINISTRATOR")
        yield client, path


def sign_in(client, username="admin"):
    return client.post("/api/auth/login", json={"username": username, "password": PASSWORD})


def test_login_me_logout_and_revoked_token(setup):
    client, path = setup
    assert client.get("/api/auth/me").status_code == 401
    response = sign_in(client, " ADMIN ")
    assert response.status_code == 200
    assert response.json()["role"] == "ADMINISTRATOR"
    assert "password_hash" not in response.json()
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=43200" in cookie
    token = client.cookies[SESSION_COOKIE]
    with connect(path) as connection:
        stored = connection.execute("SELECT token_hash FROM sessions").fetchone()[0]
    assert stored != token and stored == hash_token(token)
    assert client.get("/api/auth/me").json() == response.json()
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.set(SESSION_COOKIE, token)
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize("username,password", [("admin", "wrong"), ("missing", PASSWORD)])
def test_invalid_login(setup, username, password):
    client, _ = setup
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect username or password."}
    assert SESSION_COOKIE not in client.cookies


def test_expired_session(setup):
    client, path = setup
    sign_in(client)
    with connect(path) as connection:
        connection.execute("UPDATE sessions SET expires_at = ?", (int(time.time()) - 1,))
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/users", json=NEW_USER).status_code == 401


def test_create_requires_admin_and_verifier_can_login(setup):
    client, _ = setup
    assert client.post("/api/users", json=NEW_USER).status_code == 401
    sign_in(client)
    response = client.post("/api/users", json={**NEW_USER, "first_name": " Taylor ", "last_name": " Morgan "})
    assert response.status_code == 201
    assert response.json() == {"id": 2, "first_name": "Taylor", "last_name": "Morgan", "username": "tmorgan", "role": "VERIFIER"}
    client.post("/api/auth/logout")
    assert sign_in(client, "tmorgan").json()["role"] == "VERIFIER"
    for role in ("ADMINISTRATOR", "VERIFIER"):
        assert client.post("/api/users", json={**NEW_USER, "username": "someone", "role": role}).status_code == 403


@pytest.mark.parametrize("role", ["ADMINISTRATOR", "VERIFIER"])
def test_admin_can_assign_either_role(setup, role):
    client, _ = setup
    sign_in(client)
    response = client.post("/api/users", json={**NEW_USER, "role": role})
    assert response.status_code == 201
    assert response.json()["role"] == role
    client.post("/api/auth/logout")
    assert sign_in(client, "tmorgan").json()["role"] == role
    created = client.post("/api/users", json={**NEW_USER, "username": "someone"})
    assert created.status_code == (201 if role == "ADMINISTRATOR" else 403)


def test_duplicate_username_case_insensitive(setup):
    client, _ = setup
    sign_in(client)
    response = client.post("/api/users", json={**NEW_USER, "username": "ADMIN"})
    assert response.status_code == 409
    assert response.json()["detail"] == "That username is already in use."


@pytest.mark.parametrize("changes", [
    {"role": "SUPERUSER"}, {"permissions": "all"}, {"first_name": "   "}, {"last_name": ""}, {"first_name": "A" * 81},
    {"username": "has spaces"}, {"username": "é123"}, {"username": "ab"},
    {"username": "a" * 65}, {"password": "short"}, {"password": "p" * 129},
])
def test_invalid_user_and_extra_fields(setup, changes):
    client, path = setup
    sign_in(client)
    response = client.post("/api/users", json={**NEW_USER, **changes})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    with connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM users").fetchone()[0] == 1


def test_users_and_sessions_persist(setup):
    client, path = setup
    sign_in(client)
    client.post("/api/users", json=NEW_USER)
    token = client.cookies[SESSION_COOKIE]
    with TestClient(create_app(path)) as reopened:
        reopened.cookies.set(SESSION_COOKIE, token)
        assert reopened.get("/api/auth/me").status_code == 200
        assert sign_in(reopened, "tmorgan").status_code == 200


def test_origin_protection(setup):
    client, _ = setup
    response = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD}, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    sign_in(client)
    assert client.post("/api/users", json=NEW_USER, headers={"Origin": "null"}).status_code == 403
    assert client.post("/api/auth/logout", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.post("/api/users", json=NEW_USER, headers={"Origin": "http://testserver"}).status_code == 201


def test_login_replaces_old_session(setup):
    client, path = setup
    sign_in(client)
    old_token = client.cookies[SESSION_COOKIE]
    sign_in(client)
    assert client.cookies[SESSION_COOKIE] != old_token
    with connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM sessions").fetchone()[0] == 1
        assert connection.execute("SELECT 1 FROM sessions WHERE token_hash = ?", (hash_token(old_token),)).fetchone() is None


def test_passwords_are_salted_and_verified():
    first = hash_password(PASSWORD)
    second = hash_password(PASSWORD)
    assert first != second
    assert PASSWORD not in first
    assert verify_password(PASSWORD, first)
    assert not verify_password("wrong-password", first)


def test_secure_cookie_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("INTRAC_COOKIE_SECURE", "true")
    path = tmp_path / "secure.db"
    with TestClient(create_app(path), base_url="https://testserver") as client:
        insert_user(path, first_name="Secure", last_name="Admin", username="admin", password=PASSWORD, role="ADMINISTRATOR")
        response = sign_in(client)
        assert "; Secure" in response.headers["set-cookie"]
        assert client.get("/api/auth/me").status_code == 200


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_cookie_security_follows_request_scheme(tmp_path, monkeypatch, scheme):
    monkeypatch.delenv("INTRAC_COOKIE_SECURE", raising=False)
    path = tmp_path / "scheme.db"
    origin = f"{scheme}://testserver:5174"
    with TestClient(create_app(path), base_url=origin) as client:
        insert_user(path, first_name="System", last_name="Admin", username="admin", password=PASSWORD, role="ADMINISTRATOR")
        response = client.post(
            "/api/auth/login", json={"username": "admin", "password": PASSWORD}, headers={"Origin": origin}
        )
        assert response.status_code == 200
        assert ("; Secure" in response.headers["set-cookie"]) == (scheme == "https")
        assert client.get("/api/auth/me").status_code == 200
        other_scheme = "http" if scheme == "https" else "https"
        assert client.post("/api/auth/logout", headers={"Origin": f"{other_scheme}://testserver:5174"}).status_code == 403
        response = client.post("/api/auth/logout", headers={"Origin": origin})
        assert response.status_code == 204
        assert ("; Secure" in response.headers["set-cookie"]) == (scheme == "https")
        assert client.get("/api/auth/me").status_code == 401
