"""Integration tests for /api/users (admin-only user management)."""

from __future__ import annotations

from app.models.user import User, UserRole


# --- /api/users/ (list) --------------------------------------------------------


def test_list_users_as_admin_returns_active(
    client, admin_user, owner_user, viewer_user, login_as, db
):
    # Add an inactive user that must be filtered out
    db.add(User(email="off@example.com", role=UserRole.risk_owner, is_active=False))
    db.commit()

    login_as(admin_user)
    resp = client.get("/api/users/")
    assert resp.status_code == 200
    emails = {u["email"] for u in resp.json()}
    assert "admin@example.com" in emails
    assert "owner@example.com" in emails
    assert "viewer@example.com" in emails
    assert "off@example.com" not in emails


def test_list_users_as_analyst_returns_403(client, analyst_user, login_as):
    login_as(analyst_user)
    resp = client.get("/api/users/")
    assert resp.status_code == 403


def test_list_users_as_owner_returns_403(client, owner_user, login_as):
    login_as(owner_user)
    resp = client.get("/api/users/")
    assert resp.status_code == 403


def test_list_users_unauthenticated_returns_401(client):
    resp = client.get("/api/users/")
    assert resp.status_code == 401


# --- /api/users/assignable -----------------------------------------------------


def test_list_assignable_excludes_viewers(
    client, admin_user, owner_user, viewer_user, login_as
):
    login_as(admin_user)
    resp = client.get("/api/users/assignable")
    assert resp.status_code == 200
    roles = {u["role"] for u in resp.json()}
    assert "executive_viewer" not in roles
    emails = {u["email"] for u in resp.json()}
    assert "viewer@example.com" not in emails
    assert "owner@example.com" in emails


def test_list_assignable_as_analyst_succeeds(
    client, analyst_user, owner_user, login_as
):
    login_as(analyst_user)
    resp = client.get("/api/users/assignable")
    assert resp.status_code == 200


def test_list_assignable_as_owner_returns_403(client, owner_user, login_as):
    login_as(owner_user)
    resp = client.get("/api/users/assignable")
    assert resp.status_code == 403


def test_list_assignable_unauthenticated_returns_401(client):
    resp = client.get("/api/users/assignable")
    assert resp.status_code == 401


# --- POST /api/users/ ----------------------------------------------------------


def test_create_user_as_admin_succeeds(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.post(
        "/api/users/",
        json={
            "email": "new.user@example.com",
            "password": "a-very-long-password",
            "full_name": "New User",
            "role": "risk_owner",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "new.user@example.com"
    assert body["role"] == "risk_owner"
    assert body["is_active"] is True
    assert "hashed_password" not in body


def test_create_user_short_password_returns_422(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.post(
        "/api/users/",
        json={
            "email": "short.pw@example.com",
            "password": "short",
            "full_name": "Short PW",
        },
    )
    assert resp.status_code == 422


def test_create_user_invalid_email_returns_422(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.post(
        "/api/users/",
        json={"email": "not-an-email", "password": "long-enough-password"},
    )
    assert resp.status_code == 422


def test_create_user_duplicate_email_returns_409(client, admin_user, login_as):
    login_as(admin_user)
    payload = {
        "email": "dupe@example.com",
        "password": "long-enough-password",
        "full_name": "Dupe",
    }
    first = client.post("/api/users/", json=payload)
    assert first.status_code == 201
    second = client.post("/api/users/", json=payload)
    assert second.status_code == 409


def test_create_user_as_non_admin_returns_403(client, analyst_user, login_as):
    login_as(analyst_user)
    resp = client.post(
        "/api/users/",
        json={"email": "x@y.com", "password": "long-enough-password"},
    )
    assert resp.status_code == 403


def test_create_user_unauthenticated_returns_401(client):
    resp = client.post(
        "/api/users/",
        json={"email": "x@y.com", "password": "long-enough-password"},
    )
    assert resp.status_code == 401


# --- PATCH /api/users/{id}/deactivate ------------------------------------------


def test_deactivate_user_as_admin_succeeds(
    client, admin_user, owner_user, login_as, db
):
    login_as(admin_user)
    resp = client.patch(f"/api/users/{owner_user.id}/deactivate")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
    db.refresh(owner_user)
    assert owner_user.is_active is False


def test_deactivate_self_returns_400(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.patch(f"/api/users/{admin_user.id}/deactivate")
    assert resp.status_code == 400


def test_deactivate_missing_user_returns_404(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.patch("/api/users/9999/deactivate")
    assert resp.status_code == 404


def test_deactivate_user_as_non_admin_returns_403(
    client, owner_user, analyst_user, login_as
):
    login_as(analyst_user)
    resp = client.patch(f"/api/users/{owner_user.id}/deactivate")
    assert resp.status_code == 403


def test_deactivate_user_unauthenticated_returns_401(client, owner_user):
    resp = client.patch(f"/api/users/{owner_user.id}/deactivate")
    assert resp.status_code == 401
