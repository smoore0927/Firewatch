"""Integration tests for /api/api-keys + the Authorization: Bearer fwk_… auth path."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.models.api_key import ApiKey
from app.models.audit_log import AuditLog
from app.services import api_key_service


# --- Helpers -----------------------------------------------------------------


def _create_key(client, *, name: str = "test-key", expires_in_days: int | None = None) -> dict:
    """POST /api/api-keys and return the parsed response body."""
    payload: dict = {"name": name}
    if expires_in_days is not None:
        payload["expires_in_days"] = expires_in_days
    resp = client.post("/api/api-keys", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- Creation ----------------------------------------------------------------


def test_admin_can_create_key_and_plaintext_only_returned_once(
    client, admin_user, login_as
):
    login_as(admin_user)
    created = _create_key(client, name="ci-bot")
    assert created["name"] == "ci-bot"
    assert created["key"].startswith("fwk_")
    assert created["prefix"]
    assert created["revoked_at"] is None

    # Subsequent list MUST NOT include the plaintext key.
    listed = client.get("/api/api-keys").json()
    assert len(listed) == 1
    assert "key" not in listed[0]
    assert listed[0]["id"] == created["id"]


def test_security_analyst_can_create_key(client, analyst_user, login_as):
    login_as(analyst_user)
    created = _create_key(client, name="analyst-key")
    assert created["key"].startswith("fwk_")


def test_risk_owner_forbidden_from_creating_key(client, owner_user, login_as):
    login_as(owner_user)
    resp = client.post("/api/api-keys", json={"name": "should-fail"})
    assert resp.status_code == 403


def test_create_key_unauthenticated_returns_401(client):
    resp = client.post("/api/api-keys", json={"name": "no-auth"})
    assert resp.status_code == 401


# --- Authentication via API key ---------------------------------------------


def test_valid_api_key_authenticates_request(client, admin_user, login_as):
    login_as(admin_user)
    created = _create_key(client, name="bearer-test")
    plaintext = created["key"]
    # Clear the cookie session so we know auth comes purely from the bearer token.
    client.cookies.clear()

    resp = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {plaintext}"}
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == admin_user.email


def test_invalid_api_key_returns_401(client):
    resp = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer fwk_thisisnotarealkeyatall_x"},
    )
    assert resp.status_code == 401


def test_revoked_api_key_returns_401(client, admin_user, login_as):
    login_as(admin_user)
    created = _create_key(client, name="will-revoke")
    plaintext = created["key"]

    resp = client.delete(f"/api/api-keys/{created['id']}")
    assert resp.status_code == 204

    client.cookies.clear()
    resp = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {plaintext}"}
    )
    assert resp.status_code == 401


def test_expired_api_key_returns_401(client, admin_user, login_as, db):
    login_as(admin_user)
    created = _create_key(client, name="will-expire", expires_in_days=1)

    # Reach into the row and push expires_at into the past.
    row = db.query(ApiKey).filter(ApiKey.id == created["id"]).first()
    row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    client.cookies.clear()
    resp = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {created['key']}"}
    )
    assert resp.status_code == 401


def test_inactive_owner_key_returns_401(client, admin_user, login_as, db):
    login_as(admin_user)
    created = _create_key(client, name="will-deactivate")
    plaintext = created["key"]

    admin_user.is_active = False
    db.commit()

    client.cookies.clear()
    resp = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {plaintext}"}
    )
    assert resp.status_code == 401


def test_last_used_at_updates_after_successful_auth(
    client, admin_user, login_as, db
):
    login_as(admin_user)
    created = _create_key(client, name="track-usage")
    plaintext = created["key"]

    row = db.query(ApiKey).filter(ApiKey.id == created["id"]).first()
    assert row.last_used_at is None

    client.cookies.clear()
    resp = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {plaintext}"}
    )
    assert resp.status_code == 200

    db.expire_all()
    row = db.query(ApiKey).filter(ApiKey.id == created["id"]).first()
    assert row.last_used_at is not None


# --- Revocation rules --------------------------------------------------------


def test_non_admin_cannot_revoke_other_users_keys(
    client, admin_user, analyst_user, login_as, db
):
    """A non-admin trying to delete another user's key must return 404 (existence not leaked)."""
    # Admin creates a key.
    login_as(admin_user)
    created = _create_key(client, name="admin-key")
    # Analyst (security_analyst — privileged but not admin) tries to nuke it.
    client.cookies.clear()
    login_as(analyst_user)
    resp = client.delete(f"/api/api-keys/{created['id']}")
    assert resp.status_code == 404

    # Admin's key should still be active.
    db.expire_all()
    row = db.query(ApiKey).filter(ApiKey.id == created["id"]).first()
    assert row.revoked_at is None


def test_revoke_is_idempotent(client, admin_user, login_as):
    login_as(admin_user)
    created = _create_key(client, name="idempotent")
    first = client.delete(f"/api/api-keys/{created['id']}")
    assert first.status_code == 204
    second = client.delete(f"/api/api-keys/{created['id']}")
    assert second.status_code == 204


def test_delete_unknown_key_returns_404(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.delete("/api/api-keys/99999")
    assert resp.status_code == 404


# --- Audit logging -----------------------------------------------------------


def _latest_audit(db, *, action: str) -> AuditLog | None:
    return (
        db.query(AuditLog)
        .filter(AuditLog.action == action)
        .order_by(AuditLog.id.desc())
        .first()
    )


def test_apikey_created_audit_event_recorded_without_plaintext(
    client, admin_user, login_as, db
):
    login_as(admin_user)
    created = _create_key(client, name="audit-create")

    row = _latest_audit(db, action="apikey.created")
    assert row is not None
    assert row.user_id == admin_user.id
    assert row.resource_type == "api_key"
    assert row.resource_id == str(created["id"])
    details = json.loads(row.details)
    assert details["name"] == "audit-create"
    assert details["prefix"] == created["prefix"]
    # Plaintext must NEVER appear in any audit field.
    plaintext = created["key"]
    assert plaintext not in (row.details or "")
    assert plaintext not in (row.resource_id or "")


def test_apikey_revoked_audit_event_recorded(client, admin_user, login_as, db):
    login_as(admin_user)
    created = _create_key(client, name="audit-revoke")
    resp = client.delete(f"/api/api-keys/{created['id']}")
    assert resp.status_code == 204

    row = _latest_audit(db, action="apikey.revoked")
    assert row is not None
    assert row.user_id == admin_user.id
    assert row.resource_id == str(created["id"])
    details = json.loads(row.details)
    assert details["name"] == "audit-revoke"
    assert details["prefix"] == created["prefix"]
    assert created["key"] not in (row.details or "")


# --- Admin: list and revoke any user's keys ----------------------------------


def test_admin_can_list_all_api_keys_with_owner_info(
    client, admin_user, analyst_user, owner_user, login_as
):
    """Admin GET /api/api-keys/all returns every key with embedded owner summary."""
    # Admin mints one for themselves.
    login_as(admin_user)
    admin_key = _create_key(client, name="admin-key")
    # Analyst mints one for themselves.
    client.cookies.clear()
    login_as(analyst_user)
    analyst_key = _create_key(client, name="analyst-key")

    # Admin lists all.
    client.cookies.clear()
    login_as(admin_user)
    resp = client.get("/api/api-keys/all")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    by_id = {row["id"]: row for row in body}
    assert admin_key["id"] in by_id
    assert analyst_key["id"] in by_id

    analyst_row = by_id[analyst_key["id"]]
    assert analyst_row["owner"]["id"] == analyst_user.id
    assert analyst_row["owner"]["email"] == analyst_user.email
    assert "full_name" in analyst_row["owner"]
    # Plaintext must never appear on the list-all endpoint.
    assert "key" not in analyst_row


def test_security_analyst_forbidden_from_list_all(client, analyst_user, login_as):
    login_as(analyst_user)
    resp = client.get("/api/api-keys/all")
    assert resp.status_code == 403


def test_risk_owner_forbidden_from_list_all(client, owner_user, login_as):
    login_as(owner_user)
    resp = client.get("/api/api-keys/all")
    assert resp.status_code == 403


def test_admin_can_revoke_another_users_key(
    client, admin_user, analyst_user, login_as, db
):
    """Admin DELETE on someone else's key returns 204 and the key stops auth-ing."""
    login_as(analyst_user)
    created = _create_key(client, name="will-be-killed")
    plaintext = created["key"]

    client.cookies.clear()
    login_as(admin_user)
    resp = client.delete(f"/api/api-keys/{created['id']}")
    assert resp.status_code == 204, resp.text

    db.expire_all()
    row = db.query(ApiKey).filter(ApiKey.id == created["id"]).first()
    assert row.revoked_at is not None

    # The plaintext should no longer authenticate.
    client.cookies.clear()
    resp = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {plaintext}"}
    )
    assert resp.status_code == 401


def test_security_analyst_cannot_revoke_another_users_key(
    client, admin_user, analyst_user, login_as, db
):
    """A second security_analyst (non-admin) still gets 404 trying to revoke
    a key they don't own — the 'admins can revoke anyone' grant must NOT
    leak to other privileged roles."""
    # admin creates a key (so analyst doesn't own it).
    login_as(admin_user)
    created = _create_key(client, name="admin-key-target")

    client.cookies.clear()
    login_as(analyst_user)
    resp = client.delete(f"/api/api-keys/{created['id']}")
    assert resp.status_code == 404

    db.expire_all()
    row = db.query(ApiKey).filter(ApiKey.id == created["id"]).first()
    assert row.revoked_at is None


def test_admin_revoke_of_another_users_key_audit_details(
    client, admin_user, analyst_user, login_as, db
):
    """The admin-revocation audit row carries revoked_by_admin + target_user_email."""
    login_as(analyst_user)
    created = _create_key(client, name="audit-admin-revoke")

    client.cookies.clear()
    login_as(admin_user)
    resp = client.delete(f"/api/api-keys/{created['id']}")
    assert resp.status_code == 204

    row = _latest_audit(db, action="apikey.revoked")
    assert row is not None
    assert row.user_id == admin_user.id  # actor is the admin, not the owner
    assert row.resource_id == str(created["id"])
    details = json.loads(row.details)
    assert details["revoked_by_admin"] is True
    assert details["target_user_email"] == analyst_user.email
    assert details["name"] == "audit-admin-revoke"
    assert details["prefix"] == created["prefix"]


def test_self_revoke_audit_details_omits_admin_marker(
    client, admin_user, login_as, db
):
    """Owner revoking their own key produces audit details without revoked_by_admin."""
    login_as(admin_user)
    created = _create_key(client, name="audit-self-revoke")
    resp = client.delete(f"/api/api-keys/{created['id']}")
    assert resp.status_code == 204

    row = _latest_audit(db, action="apikey.revoked")
    assert row is not None
    details = json.loads(row.details)
    assert "revoked_by_admin" not in details


# --- Direct service-level sanity checks --------------------------------------


def test_lookup_rejects_bad_prefix(db):
    """A token that doesn't start with fwk_ never resolves to a row."""
    assert api_key_service.lookup_by_plaintext(db, "Bearer wrong") is None
    assert api_key_service.lookup_by_plaintext(db, "fwk_") is None
