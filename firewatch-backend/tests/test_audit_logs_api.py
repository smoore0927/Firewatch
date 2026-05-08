"""Integration tests for GET /api/audit/logs (admin-only audit log listing)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.audit_log import AuditLog


def _wipe(db) -> None:
    """Drop the rows that login() writes so assertions are deterministic."""
    db.query(AuditLog).delete()
    db.commit()


def _add(
    db,
    *,
    action: str = "test.event",
    user_id: int | None = None,
    user_email: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    created_at: datetime | None = None,
) -> AuditLog:
    row = AuditLog(
        action=action,
        user_id=user_id,
        user_email=user_email,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    if created_at is not None:
        row.created_at = created_at
    db.add(row)
    return row


# --- Auth + role ---------------------------------------------------------------


def test_list_audit_logs_unauthenticated_returns_401(client):
    resp = client.get("/api/audit/logs")
    assert resp.status_code == 401


@pytest.mark.parametrize(
    "user_fixture",
    ["analyst_user", "owner_user", "viewer_user"],
)
def test_list_audit_logs_as_non_admin_returns_403(
    client, login_as, request, user_fixture
):
    user = request.getfixturevalue(user_fixture)
    login_as(user)
    resp = client.get("/api/audit/logs")
    assert resp.status_code == 403


# --- Empty state ---------------------------------------------------------------


def test_list_audit_logs_empty_returns_zero_total(client, admin_user, login_as, db):
    login_as(admin_user)
    _wipe(db)
    resp = client.get("/api/audit/logs")
    assert resp.status_code == 200
    assert resp.json() == {"total": 0, "items": []}


# --- Filters -------------------------------------------------------------------


def test_list_audit_logs_filter_by_action(client, admin_user, login_as, db):
    login_as(admin_user)
    _wipe(db)
    _add(db, action="risk.created")
    _add(db, action="risk.updated")
    _add(db, action="auth.login.success")
    db.commit()

    resp = client.get("/api/audit/logs?action=risk.created")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["action"] == "risk.created"


def test_list_audit_logs_filter_by_user_id(client, admin_user, login_as, db):
    login_as(admin_user)
    _wipe(db)
    _add(db, action="x", user_id=admin_user.id)
    _add(db, action="x", user_id=999)
    db.commit()

    resp = client.get(f"/api/audit/logs?user_id={admin_user.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["user_id"] == admin_user.id


def test_list_audit_logs_filter_by_resource_type(client, admin_user, login_as, db):
    login_as(admin_user)
    _wipe(db)
    _add(db, action="risk.created", resource_type="risk")
    _add(db, action="user.created", resource_type="user")
    db.commit()

    resp = client.get("/api/audit/logs?resource_type=risk")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["resource_type"] == "risk"


def test_list_audit_logs_filter_by_date_range(client, admin_user, login_as, db):
    login_as(admin_user)
    _wipe(db)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    two_days_ago = now - timedelta(days=2)
    one_day_ago = now - timedelta(days=1)
    _add(db, action="old", created_at=two_days_ago)
    _add(db, action="mid", created_at=one_day_ago)
    _add(db, action="new", created_at=now)
    db.commit()

    # start filter: >= one_day_ago should drop "old"
    resp = client.get("/api/audit/logs", params={"start": one_day_ago.isoformat()})
    body = resp.json()
    actions = {it["action"] for it in body["items"]}
    assert body["total"] == 2
    assert actions == {"mid", "new"}

    # end filter: <= one_day_ago should drop "new"
    resp = client.get("/api/audit/logs", params={"end": one_day_ago.isoformat()})
    body = resp.json()
    actions = {it["action"] for it in body["items"]}
    assert body["total"] == 2
    assert actions == {"old", "mid"}

    # combined: only "mid" satisfies both bounds
    resp = client.get(
        "/api/audit/logs",
        params={
            "start": one_day_ago.isoformat(),
            "end": one_day_ago.isoformat(),
        },
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["action"] == "mid"


def test_list_audit_logs_combined_filters_intersect(client, admin_user, login_as, db):
    login_as(admin_user)
    _wipe(db)
    # action matches but user_id doesn't
    _add(db, action="risk.created", user_id=999)
    # action and user_id both match
    _add(db, action="risk.created", user_id=admin_user.id)
    # user_id matches but action doesn't
    _add(db, action="risk.updated", user_id=admin_user.id)
    db.commit()

    # Either filter alone returns 2 rows; together they return only 1.
    only_action = client.get("/api/audit/logs?action=risk.created").json()
    only_user = client.get(f"/api/audit/logs?user_id={admin_user.id}").json()
    combined = client.get(
        f"/api/audit/logs?action=risk.created&user_id={admin_user.id}"
    ).json()

    assert only_action["total"] == 2
    assert only_user["total"] == 2
    assert combined["total"] == 1
    assert combined["items"][0]["action"] == "risk.created"
    assert combined["items"][0]["user_id"] == admin_user.id


# --- Pagination + ordering -----------------------------------------------------


def test_list_audit_logs_pagination_skip_limit(client, admin_user, login_as, db):
    login_as(admin_user)
    _wipe(db)
    for i in range(7):
        _add(db, action=f"evt-{i}")
    db.commit()

    resp = client.get("/api/audit/logs?skip=2&limit=3")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 7
    assert len(body["items"]) == 3


def test_list_audit_logs_limit_max_is_200(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.get("/api/audit/logs?limit=201")
    assert resp.status_code == 422


def test_list_audit_logs_default_limit_is_50(client, admin_user, login_as, db):
    login_as(admin_user)
    _wipe(db)
    for i in range(60):
        _add(db, action=f"evt-{i}")
    db.commit()

    resp = client.get("/api/audit/logs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 60
    assert len(body["items"]) == 50


def test_list_audit_logs_orders_by_created_at_desc_with_id_tiebreak(
    client, admin_user, login_as, db
):
    login_as(admin_user)
    _wipe(db)
    same_time = datetime.now(timezone.utc).replace(microsecond=0)
    _add(db, action="first", created_at=same_time)
    _add(db, action="second", created_at=same_time)
    db.commit()

    resp = client.get("/api/audit/logs")
    body = resp.json()
    assert body["total"] == 2
    # Higher id (the second insert) must come first when created_at ties.
    assert body["items"][0]["action"] == "second"
    assert body["items"][1]["action"] == "first"
    assert body["items"][0]["id"] > body["items"][1]["id"]
