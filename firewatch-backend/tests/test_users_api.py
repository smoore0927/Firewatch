"""Integration tests for /api/users (admin-only user management)."""

from __future__ import annotations

from app.models.audit_log import AuditLog
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
            "password": "NewUserPass123!",
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


def test_user_create_rejects_weak_password(client, admin_user, login_as):
    """The new password policy must reject passwords that miss any complexity rule."""
    login_as(admin_user)
    resp = client.post(
        "/api/users/",
        json={
            "email": "weak.pw@example.com",
            "password": "weakpass",
            "full_name": "Weak PW",
        },
    )
    assert resp.status_code == 422
    msg = " ".join(err.get("msg", "") for err in resp.json().get("detail", []))
    assert "Password must" in msg
    # weakpass is too short, lacks uppercase, digit, and special character
    assert "12 characters" in msg or "uppercase" in msg or "digit" in msg or "special" in msg


def test_create_user_invalid_email_returns_422(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.post(
        "/api/users/",
        json={"email": "not-an-email", "password": "NewUserPass123!"},
    )
    assert resp.status_code == 422


def test_create_user_duplicate_email_returns_409(client, admin_user, login_as):
    login_as(admin_user)
    payload = {
        "email": "dupe@example.com",
        "password": "NewUserPass123!",
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
        json={"email": "x@y.com", "password": "NewUserPass123!"},
    )
    assert resp.status_code == 403


def test_create_user_unauthenticated_returns_401(client):
    resp = client.post(
        "/api/users/",
        json={"email": "x@y.com", "password": "NewUserPass123!"},
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


# --- PATCH /api/users/{id}/role ------------------------------------------------


def test_change_role_as_admin_succeeds(
    client, admin_user, viewer_user, login_as, db
):
    login_as(admin_user)
    resp = client.patch(
        f"/api/users/{viewer_user.id}/role", json={"role": "risk_owner"}
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "risk_owner"
    db.refresh(viewer_user)
    assert viewer_user.role == UserRole.risk_owner

    audit = (
        db.query(AuditLog)
        .filter(
            AuditLog.action == "user.role.changed",
            AuditLog.resource_id == str(viewer_user.id),
        )
        .one()
    )
    assert audit.details is not None
    import json as _json
    payload = _json.loads(audit.details)
    assert payload["from"] == "executive_viewer"
    assert payload["to"] == "risk_owner"


def test_change_role_as_non_admin_returns_403(
    client, owner_user, viewer_user, login_as
):
    login_as(owner_user)
    resp = client.patch(
        f"/api/users/{viewer_user.id}/role", json={"role": "risk_owner"}
    )
    assert resp.status_code == 403


def test_change_role_unauthenticated_returns_401(client, viewer_user):
    resp = client.patch(
        f"/api/users/{viewer_user.id}/role", json={"role": "risk_owner"}
    )
    assert resp.status_code == 401


def test_change_role_target_not_found_returns_404(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.patch("/api/users/9999/role", json={"role": "risk_owner"})
    assert resp.status_code == 404


def test_change_role_for_sso_user_returns_400(client, admin_user, login_as, db):
    sso_user = User(
        email="sso@example.com",
        full_name="SSO User",
        hashed_password=None,
        role=UserRole.risk_owner,
        auth_provider="oidc",
        external_id="sso-sub-1",
        is_active=True,
    )
    db.add(sso_user)
    db.commit()
    db.refresh(sso_user)

    login_as(admin_user)
    resp = client.patch(
        f"/api/users/{sso_user.id}/role", json={"role": "security_analyst"}
    )
    assert resp.status_code == 400
    assert "SSO-provisioned" in resp.json()["detail"]


def test_change_own_role_returns_400(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.patch(
        f"/api/users/{admin_user.id}/role", json={"role": "risk_owner"}
    )
    assert resp.status_code == 400
    assert "your own role" in resp.json()["detail"]


def test_demote_other_admin_succeeds_when_self_still_admin(
    client, admin_user, login_as, db
):
    """Demoting another admin while the caller remains admin should succeed."""
    other_admin = User(
        email="admin2@example.com",
        full_name="Admin Two",
        hashed_password="$argon2id$dummyhash",
        role=UserRole.admin,
        auth_provider="local",
        is_active=True,
    )
    db.add(other_admin)
    db.commit()
    db.refresh(other_admin)

    login_as(admin_user)
    resp = client.patch(
        f"/api/users/{other_admin.id}/role", json={"role": "risk_owner"}
    )
    assert resp.status_code == 200
    db.refresh(other_admin)
    assert other_admin.role == UserRole.risk_owner


def test_change_role_no_op_returns_200_no_audit(
    client, admin_user, owner_user, login_as, db
):
    login_as(admin_user)
    resp = client.patch(
        f"/api/users/{owner_user.id}/role", json={"role": "risk_owner"}
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "risk_owner"

    audit_count = (
        db.query(AuditLog)
        .filter(
            AuditLog.action == "user.role.changed",
            AuditLog.resource_id == str(owner_user.id),
        )
        .count()
    )
    assert audit_count == 0


# --- seeded admin (must_change_password=False) is not gated --------------------


def test_seeded_admin_not_gated_by_first_login_flow(
    client, admin_user, login_as, db
):
    """Existing admin (default-False flag) keeps full access to admin routes."""
    assert admin_user.must_change_password is False
    login_as(admin_user)

    # List users (admin-only) still works.
    resp = client.get("/api/users/")
    assert resp.status_code == 200

    # Creating users still works.
    resp = client.post(
        "/api/users/",
        json={
            "email": "downstream@example.com",
            "password": "DownstreamPass1!",
            "full_name": "Downstream",
            "role": "risk_owner",
        },
    )
    assert resp.status_code == 201
