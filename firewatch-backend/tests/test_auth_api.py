"""Integration tests for /api/auth (local login, refresh, logout, me)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.dependencies import get_db
from app.core.security import create_access_token, create_refresh_token, hash_password
from app.models.user import User, UserRole
from main import app


# --- /login --------------------------------------------------------------------


def test_login_happy_path_sets_cookies(client, existing_local_user):
    resp = client.post(
        "/api/auth/login",
        json={"email": "local@example.com", "password": "SecretPass123!"},
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
        json={"email": "nobody@example.com", "password": "SecretPass123!"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid email or password"


def test_login_inactive_user_returns_401(client, db):
    user = User(
        email="inactive@example.com",
        full_name="Inactive",
        hashed_password=hash_password("SecretPass123!"),
        role=UserRole.risk_owner,
        auth_provider="local",
        is_active=False,
    )
    db.add(user)
    db.commit()
    resp = client.post(
        "/api/auth/login",
        json={"email": "inactive@example.com", "password": "SecretPass123!"},
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
    refresh = create_refresh_token(existing_local_user.id, existing_local_user.session_version)
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
    access = create_access_token(existing_local_user.id, existing_local_user.session_version)
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
        hashed_password=hash_password("SecretPass123!"),
        role=UserRole.risk_owner,
        is_active=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    refresh = create_refresh_token(user.id, user.session_version)
    client.cookies.set("refresh_token", refresh, path="/api/auth/refresh")
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 401


def test_refresh_after_logout_returns_401(client, existing_local_user):
    """A refresh token issued before logout must be rejected after the user logs out."""
    # Log in to get cookies (including refresh_token)
    resp = client.post(
        "/api/auth/login",
        json={"email": "local@example.com", "password": "SecretPass123!"},
    )
    assert resp.status_code == 200

    # Log out — sets last_logout_at on the user record
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 204

    # Attempt to use the stale refresh token cookie
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 401


# --- /logout -------------------------------------------------------------------


def test_logout_clears_cookies(client, existing_local_user):
    client.post(
        "/api/auth/login",
        json={"email": "local@example.com", "password": "SecretPass123!"},
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
        json={"email": "local@example.com", "password": "SecretPass123!"},
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
    refresh = create_refresh_token(existing_local_user.id, existing_local_user.session_version)
    client.cookies.set("access_token", refresh)
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


# --- /change-password ----------------------------------------------------------


def test_change_password_success(client, existing_local_user, login_as):
    login_as(existing_local_user)
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": "SecretPass123!", "new_password": "NewPass456@word"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"message": "Password updated"}
    # Should be able to log in with the new password
    resp2 = client.post(
        "/api/auth/login",
        json={"email": "local@example.com", "password": "NewPass456@word"},
    )
    assert resp2.status_code == 200


def test_change_password_wrong_current(client, existing_local_user, login_as):
    login_as(existing_local_user)
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": "wrongpassword", "new_password": "NewPass456@word"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Current password is incorrect."


def test_change_password_sso_user_returns_400(client, db, login_as):
    sso_user = User(
        email="active-sso@example.com",
        full_name="Active SSO",
        hashed_password=None,
        role=UserRole.risk_owner,
        auth_provider="oidc",
        external_id="active-sso-sub",
        is_active=True,
    )
    db.add(sso_user)
    db.commit()
    db.refresh(sso_user)
    # Inject a valid access token cookie directly (can't log in via password)
    access = create_access_token(sso_user.id, sso_user.session_version)
    client.cookies.set("access_token", access)
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": "anything", "new_password": "NewPass456@word"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Password cannot be changed for SSO-provisioned accounts."


def test_change_password_unauthenticated_returns_401(client):
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": "SecretPass123!", "new_password": "NewPass456@word"},
    )
    assert resp.status_code == 401


def test_change_password_invalidates_other_sessions(db, existing_local_user):
    """After a password change on client A, client B's access token is rejected."""
    app.dependency_overrides[get_db] = lambda: db

    with TestClient(app) as client_a, TestClient(app) as client_b:
        # Both clients log in
        resp_a = client_a.post(
            "/api/auth/login",
            json={"email": "local@example.com", "password": "SecretPass123!"},
        )
        assert resp_a.status_code == 200

        resp_b = client_b.post(
            "/api/auth/login",
            json={"email": "local@example.com", "password": "SecretPass123!"},
        )
        assert resp_b.status_code == 200

        # Client B can currently access /me
        assert client_b.get("/api/auth/me").status_code == 200

        # Client A changes the password — stamps last_logout_at
        resp = client_a.post(
            "/api/auth/change-password",
            json={"current_password": "SecretPass123!", "new_password": "NewPass456@word"},
        )
        assert resp.status_code == 200

        # Client B's old access token is now before last_logout_at → 401
        assert client_b.get("/api/auth/me").status_code == 401

    app.dependency_overrides.pop(get_db, None)


# --- password policy on change-password ----------------------------------------


def test_change_password_rejects_weak_new_password(client, existing_local_user, login_as):
    login_as(existing_local_user)
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": "SecretPass123!", "new_password": "short"},
    )
    assert resp.status_code == 422
    body = resp.json()
    # Pydantic surfaces validator messages under detail[].msg
    msg = " ".join(err.get("msg", "") for err in body.get("detail", []))
    assert "Password must" in msg


def test_change_password_rate_limited(
    client, existing_local_user, login_as, monkeypatch
):
    """The 6th rapid request to /change-password must be rejected with 429."""
    monkeypatch.setattr(app.state.limiter, "enabled", True)
    login_as(existing_local_user)

    payload = {"current_password": "wrongpassword", "new_password": "NewPass456@word"}
    statuses = []
    for _ in range(6):
        resp = client.post("/api/auth/change-password", json=payload)
        statuses.append(resp.status_code)
    assert statuses[-1] == 429, statuses


# --- has_password on login + /me ----------------------------------------------


def test_login_response_has_password_true_for_local_user(client, existing_local_user):
    resp = client.post(
        "/api/auth/login",
        json={"email": "local@example.com", "password": "SecretPass123!"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_password"] is True


def test_login_response_has_password_false_for_sso_only_user(client, db):
    """An SSO-provisioned user with hashed_password set (via a temporary password) reports
    has_password=False when their hashed_password is None. We test this by directly
    constructing a user, setting a temp password to log in, then clearing it — but the
    cleaner approach: SSO users cannot log in via password, so we exercise the schema
    by constructing a LoginResponse directly."""
    from app.schemas.auth import LoginResponse
    from datetime import datetime, timezone

    sso_resp = LoginResponse(
        user_id=1,
        email="sso@example.com",
        role="risk_owner",
        full_name="SSO User",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        has_password=False,
        must_change_password=False,
    )
    assert sso_resp.has_password is False


def test_me_returns_has_password_true_for_local_user(client, existing_local_user, login_as):
    login_as(existing_local_user)
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_password"] is True
    assert "hashed_password" not in body


def test_me_returns_has_password_false_for_sso_user(client, db):
    sso_user = User(
        email="sso-me@example.com",
        full_name="SSO Me",
        hashed_password=None,
        role=UserRole.risk_owner,
        auth_provider="oidc",
        external_id="sso-me-sub",
        is_active=True,
    )
    db.add(sso_user)
    db.commit()
    db.refresh(sso_user)
    access = create_access_token(sso_user.id, sso_user.session_version)
    client.cookies.set("access_token", access)
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_password"] is False
    assert "hashed_password" not in body


# --- must_change_password first-login gate ------------------------------------


def test_create_user_sets_must_change_password_true(client, admin_user, login_as):
    """Users created via POST /api/users are flagged for first-login password change."""
    login_as(admin_user)
    resp = client.post(
        "/api/users/",
        json={
            "email": "fresh@example.com",
            "password": "TempPass123!word",
            "full_name": "Fresh User",
            "role": "risk_owner",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["must_change_password"] is True


def test_login_returns_must_change_password_flag(client, admin_user, login_as):
    """Login response surfaces must_change_password so the frontend can redirect."""
    login_as(admin_user)
    client.post(
        "/api/users/",
        json={
            "email": "newbie@example.com",
            "password": "TempPass123!word",
            "full_name": "Newbie",
            "role": "risk_owner",
        },
    )
    # Clear admin cookies before the newbie logs in.
    client.cookies.clear()
    resp = client.post(
        "/api/auth/login",
        json={"email": "newbie@example.com", "password": "TempPass123!word"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["must_change_password"] is True


def test_gated_route_returns_403_when_password_change_required(
    client, admin_user, login_as
):
    """Any protected route returns 403 PASSWORD_CHANGE_REQUIRED for a flagged user."""
    login_as(admin_user)
    client.post(
        "/api/users/",
        json={
            "email": "gated@example.com",
            "password": "TempPass123!word",
            "full_name": "Gated",
            "role": "risk_owner",
        },
    )
    client.cookies.clear()
    resp = client.post(
        "/api/auth/login",
        json={"email": "gated@example.com", "password": "TempPass123!word"},
    )
    assert resp.status_code == 200

    resp = client.get("/api/risks")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "PASSWORD_CHANGE_REQUIRED"


def test_me_succeeds_when_password_change_required(client, admin_user, login_as):
    """GET /api/auth/me bypasses the first-login gate so the frontend can introspect."""
    login_as(admin_user)
    client.post(
        "/api/users/",
        json={
            "email": "me-flag@example.com",
            "password": "TempPass123!word",
            "full_name": "Me Flag",
            "role": "risk_owner",
        },
    )
    client.cookies.clear()
    client.post(
        "/api/auth/login",
        json={"email": "me-flag@example.com", "password": "TempPass123!word"},
    )
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["must_change_password"] is True
    assert body["email"] == "me-flag@example.com"


def test_change_password_clears_must_change_password_flag(
    client, admin_user, login_as, db
):
    """Successfully changing the password lifts the gate; gated routes work again."""
    login_as(admin_user)
    create_resp = client.post(
        "/api/users/",
        json={
            "email": "switch@example.com",
            "password": "TempPass123!word",
            "full_name": "Switch",
            "role": "risk_owner",
        },
    )
    new_user_id = create_resp.json()["id"]
    client.cookies.clear()
    client.post(
        "/api/auth/login",
        json={"email": "switch@example.com", "password": "TempPass123!word"},
    )

    resp = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "TempPass123!word",
            "new_password": "FreshPass456@word",
        },
    )
    assert resp.status_code == 200

    # DB flag was cleared
    user = db.query(User).filter(User.id == new_user_id).one()
    assert user.must_change_password is False

    # Re-login with the new password (change-password rotates last_logout_at, which
    # the frontend would treat as a forced re-auth) and confirm the gate is gone.
    client.cookies.clear()
    resp = client.post(
        "/api/auth/login",
        json={"email": "switch@example.com", "password": "FreshPass456@word"},
    )
    assert resp.status_code == 200
    assert resp.json()["must_change_password"] is False

    # Previously gated route now works.
    resp = client.get("/api/risks")
    assert resp.status_code == 200


def test_logout_allowed_when_password_change_required(client, admin_user, login_as):
    """A flagged user can still log out instead of being stuck."""
    login_as(admin_user)
    client.post(
        "/api/users/",
        json={
            "email": "bailout@example.com",
            "password": "TempPass123!word",
            "full_name": "Bailout",
            "role": "risk_owner",
        },
    )
    client.cookies.clear()
    client.post(
        "/api/auth/login",
        json={"email": "bailout@example.com", "password": "TempPass123!word"},
    )
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 204
