"""Integration tests for /api/auth (local login, refresh, logout, me)."""

from __future__ import annotations

from app.core.security import create_access_token, create_refresh_token, hash_password
from app.models.user import User, UserRole


# --- /login --------------------------------------------------------------------


def test_login_happy_path_sets_cookies(client, existing_local_user):
    resp = client.post(
        "/api/auth/login",
        json={"email": "local@example.com", "password": "secret123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "local@example.com"
    assert body["role"] == "risk_owner"
    assert body["user_id"] == existing_local_user.id
    assert body["is_active"] is True
    assert "access_token" in resp.cookies
    assert "refresh_token" in resp.cookies


def test_login_wrong_password_returns_401(client, existing_local_user):
    resp = client.post(
        "/api/auth/login",
        json={"email": "local@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid email or password"
    assert "access_token" not in resp.cookies


def test_login_unknown_user_returns_401(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "secret123"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid email or password"


def test_login_inactive_user_returns_401(client, db):
    user = User(
        email="inactive@example.com",
        full_name="Inactive",
        hashed_password=hash_password("secret123"),
        role=UserRole.risk_owner,
        auth_provider="local",
        is_active=False,
    )
    db.add(user)
    db.commit()
    resp = client.post(
        "/api/auth/login",
        json={"email": "inactive@example.com", "password": "secret123"},
    )
    assert resp.status_code == 401


def test_login_sso_only_user_with_password_attempt_returns_401(client, db):
    """SSO-only users have hashed_password=None — must not crash, must return 401."""
    user = User(
        email="ssoonly@example.com",
        full_name="SSO Only",
        hashed_password=None,
        role=UserRole.risk_owner,
        auth_provider="oidc",
        external_id="sub-sso-only",
        is_active=True,
    )
    db.add(user)
    db.commit()
    resp = client.post(
        "/api/auth/login",
        json={"email": "ssoonly@example.com", "password": "any-password"},
    )
    assert resp.status_code == 401


def test_login_missing_field_returns_422(client):
    resp = client.post("/api/auth/login", json={"email": "a@b.c"})
    assert resp.status_code == 422


# --- /refresh ------------------------------------------------------------------


def test_refresh_with_valid_cookie_issues_new_access_token(client, existing_local_user):
    refresh = create_refresh_token(existing_local_user.id)
    client.cookies.set("refresh_token", refresh, path="/api/auth/refresh")
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 200
    assert resp.json() == {"message": "Token refreshed"}
    assert "access_token" in resp.cookies


def test_refresh_without_cookie_returns_401(client):
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or expired refresh token"


def test_refresh_with_access_token_in_refresh_slot_returns_401(client, existing_local_user):
    """An access token must not be accepted as a refresh token (type claim guard)."""
    access = create_access_token(existing_local_user.id)
    client.cookies.set("refresh_token", access, path="/api/auth/refresh")
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 401


def test_refresh_with_garbage_token_returns_401(client):
    client.cookies.set("refresh_token", "not-a-jwt", path="/api/auth/refresh")
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 401


def test_refresh_for_inactive_user_returns_401(client, db):
    user = User(
        email="gone@example.com",
        hashed_password=hash_password("secret123"),
        role=UserRole.risk_owner,
        is_active=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    refresh = create_refresh_token(user.id)
    client.cookies.set("refresh_token", refresh, path="/api/auth/refresh")
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 401


# --- /logout -------------------------------------------------------------------


def test_logout_clears_cookies(client, existing_local_user):
    client.post(
        "/api/auth/login",
        json={"email": "local@example.com", "password": "secret123"},
    )
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 204
    set_cookies = [
        v for k, v in resp.headers.multi_items() if k.lower() == "set-cookie"
    ]
    assert any("access_token=" in c and "Max-Age=0" in c for c in set_cookies)
    assert any("refresh_token=" in c and "Max-Age=0" in c for c in set_cookies)


# --- /me -----------------------------------------------------------------------


def test_me_authenticated_returns_user(client, existing_local_user):
    client.post(
        "/api/auth/login",
        json={"email": "local@example.com", "password": "secret123"},
    )
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "local@example.com"
    assert body["role"] == "risk_owner"
    assert body["id"] == existing_local_user.id
    assert "hashed_password" not in body


def test_me_unauthenticated_returns_401(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not authenticated"


def test_me_with_garbage_cookie_returns_401(client):
    client.cookies.set("access_token", "not-a-jwt")
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_with_refresh_token_in_access_slot_returns_401(client, existing_local_user):
    """A refresh token must not authenticate via access_token cookie."""
    refresh = create_refresh_token(existing_local_user.id)
    client.cookies.set("access_token", refresh)
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401
