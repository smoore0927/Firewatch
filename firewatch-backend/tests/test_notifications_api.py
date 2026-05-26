"""Integration tests for /api/notifications routes."""

from __future__ import annotations

from app.models.notification import Notification, NotificationType
from app.services import notification_service


def _seed(db, *, user_id: int, **overrides) -> Notification:
    kwargs = dict(
        user_id=user_id,
        type=NotificationType.risk_changed,
        risk_id=None,
        payload={},
        link="/x",
        title="t",
        message="m",
    )
    kwargs.update(overrides)
    row = notification_service.create_notification(db, **kwargs)
    assert row is not None
    return row


def test_list_requires_auth(client):
    resp = client.get("/api/notifications")
    assert resp.status_code == 401


def test_unread_count_requires_auth(client):
    resp = client.get("/api/notifications/unread-count")
    assert resp.status_code == 401


def test_mark_read_requires_auth(client):
    resp = client.post("/api/notifications/1/read")
    assert resp.status_code == 401


def test_list_returns_only_callers_rows(client, owner_user, owner_user_b, login_as, db):
    _seed(db, user_id=owner_user.id, title="for me")
    _seed(db, user_id=owner_user_b.id, title="for other")
    login_as(owner_user)
    resp = client.get("/api/notifications")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["unread_total"] == 1
    assert body["items"][0]["title"] == "for me"


def test_list_unread_only_filters(client, owner_user, login_as, db):
    n1 = _seed(db, user_id=owner_user.id, title="unread one")
    n2 = _seed(db, user_id=owner_user.id, title="read one")
    notification_service.mark_read(db, owner_user.id, n2.id)
    login_as(owner_user)
    resp = client.get("/api/notifications?unread_only=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2  # total ignores filter
    assert body["unread_total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == n1.id


def test_unread_count_endpoint(client, owner_user, login_as, db):
    _seed(db, user_id=owner_user.id)
    _seed(db, user_id=owner_user.id)
    login_as(owner_user)
    resp = client.get("/api/notifications/unread-count")
    assert resp.status_code == 200
    assert resp.json() == {"count": 2}


def test_mark_one_read_returns_204(client, owner_user, login_as, db):
    n = _seed(db, user_id=owner_user.id)
    login_as(owner_user)
    resp = client.post(f"/api/notifications/{n.id}/read")
    assert resp.status_code == 204
    db.expire_all()
    refreshed = db.query(Notification).filter(Notification.id == n.id).first()
    assert refreshed.read_at is not None


def test_mark_one_read_404_for_other_users_notification(
    client, owner_user, owner_user_b, login_as, db
):
    n = _seed(db, user_id=owner_user_b.id)
    login_as(owner_user)
    resp = client.post(f"/api/notifications/{n.id}/read")
    assert resp.status_code == 404


def test_mark_all_read_only_affects_caller(client, owner_user, owner_user_b, login_as, db):
    _seed(db, user_id=owner_user.id)
    _seed(db, user_id=owner_user.id)
    _seed(db, user_id=owner_user_b.id)
    login_as(owner_user)
    resp = client.post("/api/notifications/mark-all-read")
    assert resp.status_code == 200
    assert resp.json() == {"marked": 2}
    assert notification_service.unread_count(db, owner_user.id) == 0
    assert notification_service.unread_count(db, owner_user_b.id) == 1
