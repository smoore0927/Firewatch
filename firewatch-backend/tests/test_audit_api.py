"""Integration tests for /api/audit (admin-only audit log read API)."""

from __future__ import annotations

from app.models.audit_log import AuditLog


def _add_action(db, action: str, *, user_email: str = "x@example.com") -> None:
    db.add(AuditLog(action=action, user_email=user_email))


# --- GET /api/audit/actions ----------------------------------------------------


def test_list_audit_actions_empty(client, admin_user, login_as, db):
    login_as(admin_user)
    # Wipe any rows the login flow itself wrote so the table is truly empty.
    db.query(AuditLog).delete()
    db.commit()

    resp = client.get("/api/audit/actions")
    assert resp.status_code == 200
    assert resp.json() == {"actions": []}


def test_list_audit_actions_returns_sorted_distinct(
    client, admin_user, login_as, db
):
    login_as(admin_user)
    # Drop any login-side rows so the assertion is deterministic.
    db.query(AuditLog).delete()
    db.commit()

    _add_action(db, "user.login")
    _add_action(db, "risk.created")
    _add_action(db, "user.login")  # duplicate
    _add_action(db, "audit.exported")
    db.commit()

    resp = client.get("/api/audit/actions")
    assert resp.status_code == 200
    assert resp.json() == {
        "actions": ["audit.exported", "risk.created", "user.login"]
    }


def test_list_audit_actions_as_non_admin_returns_403(
    client, analyst_user, login_as
):
    login_as(analyst_user)
    resp = client.get("/api/audit/actions")
    assert resp.status_code == 403


def test_list_audit_actions_unauthenticated_returns_401(client):
    resp = client.get("/api/audit/actions")
    assert resp.status_code == 401
