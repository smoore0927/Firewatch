"""End-to-end instrumentation tests: confirm audited routes write the right rows.

SSO instrumentation (app/api/sso.py) is intentionally not covered here — its
hooks fire deep inside the OIDC discovery/exchange flow, which would require
heavy mocking. Coverage of the SSO record_event sites remains an open gap.
"""

from __future__ import annotations

import json

from app.models.audit_log import AuditLog


def _latest(db, *, action: str | None = None) -> AuditLog | None:
    """Return the highest-id audit row (optionally filtered by action)."""
    q = db.query(AuditLog)
    if action is not None:
        q = q.filter(AuditLog.action == action)
    return q.order_by(AuditLog.id.desc()).first()


# --- /api/auth ----------------------------------------------------------------


def test_login_success_records_audit_row(client, existing_local_user, db):
    resp = client.post(
        "/api/auth/login",
        json={"email": "local@example.com", "password": "SecretPass123!"},
    )
    assert resp.status_code == 200

    row = _latest(db, action="auth.login.success")
    assert row is not None
    assert row.user_id == existing_local_user.id
    assert row.user_email == existing_local_user.email
    assert row.ip_address  # TestClient sets a client tuple, so this should be populated
    assert json.loads(row.details) == {"method": "password"}


def test_login_failure_records_audit_row_with_attempted_email(
    client, existing_local_user, db
):
    resp = client.post(
        "/api/auth/login",
        json={"email": "local@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401

    row = _latest(db, action="auth.login.failed")
    assert row is not None
    assert row.user_id is None
    assert row.user_email == "local@example.com"
    assert json.loads(row.details) == {"reason": "invalid_credentials"}


def test_logout_records_audit_row(client, existing_local_user, login_as, db):
    login_as(existing_local_user)
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 204

    row = _latest(db, action="auth.logout")
    assert row is not None
    assert row.user_id == existing_local_user.id


def test_refresh_failure_records_audit_row(client, db):
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 401

    row = _latest(db, action="auth.refresh.failed")
    assert row is not None
    payload = json.loads(row.details)
    assert "reason" in payload


# --- /api/users --------------------------------------------------------------


def test_create_user_records_audit_row(client, admin_user, login_as, db):
    login_as(admin_user)
    resp = client.post(
        "/api/users/",
        json={
            "email": "audited.create@example.com",
            "password": "NewUserPass123!",
            "full_name": "Audited Create",
            "role": "risk_owner",
        },
    )
    assert resp.status_code == 201
    new_user_id = resp.json()["id"]

    row = _latest(db, action="user.created")
    assert row is not None
    assert row.resource_type == "user"
    assert row.resource_id == str(new_user_id)
    assert row.user_id == admin_user.id
    payload = json.loads(row.details)
    assert payload["created_email"] == "audited.create@example.com"
    assert payload["role"] == "risk_owner"


def test_deactivate_user_records_audit_row(
    client, admin_user, owner_user, login_as, db
):
    login_as(admin_user)
    resp = client.patch(f"/api/users/{owner_user.id}/deactivate")
    assert resp.status_code == 200

    row = _latest(db, action="user.deactivated")
    assert row is not None
    assert row.resource_type == "user"
    assert row.resource_id == str(owner_user.id)
    assert row.user_id == admin_user.id


# --- /api/risks --------------------------------------------------------------


def _risk_payload(**overrides) -> dict:
    base = {
        "title": "Audited risk",
        "description": "for audit instrumentation tests",
        "likelihood": 2,
        "impact": 3,
    }
    base.update(overrides)
    return base


def test_create_risk_records_audit_row(client, admin_user, login_as, db):
    login_as(admin_user)
    resp = client.post("/api/risks", json=_risk_payload())
    assert resp.status_code == 201

    row = _latest(db, action="risk.created")
    assert row is not None
    assert row.resource_type == "risk"
    assert row.resource_id == "RISK-001"
    assert row.user_id == admin_user.id


def test_update_risk_records_audit_row(client, admin_user, login_as, db):
    login_as(admin_user)
    created = client.post("/api/risks", json=_risk_payload()).json()
    resp = client.put(
        f"/api/risks/{created['risk_id']}",
        json={"title": "Updated for audit"},
    )
    assert resp.status_code == 200

    row = _latest(db, action="risk.updated")
    assert row is not None
    assert row.resource_type == "risk"
    assert row.resource_id == created["risk_id"]


def test_delete_risk_records_audit_row(client, admin_user, login_as, db):
    login_as(admin_user)
    created = client.post("/api/risks", json=_risk_payload()).json()
    resp = client.delete(f"/api/risks/{created['risk_id']}")
    assert resp.status_code == 204

    row = _latest(db, action="risk.deleted")
    assert row is not None
    assert row.resource_type == "risk"
    assert row.resource_id == created["risk_id"]


def test_assessment_added_records_audit_row(client, admin_user, login_as, db):
    login_as(admin_user)
    created = client.post("/api/risks", json=_risk_payload()).json()
    resp = client.post(
        f"/api/risks/{created['risk_id']}/assessments",
        json={"likelihood": 4, "impact": 5},
    )
    assert resp.status_code == 200

    row = _latest(db, action="risk.assessment.added")
    assert row is not None
    assert row.resource_type == "risk"
    assert row.resource_id == created["risk_id"]
    payload = json.loads(row.details)
    assert payload == {"likelihood": 4, "impact": 5}
