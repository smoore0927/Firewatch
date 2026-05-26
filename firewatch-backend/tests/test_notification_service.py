"""Unit tests for the notification persistence service + event subscribers."""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from app.models.notification import Notification, NotificationType
from app.models.risk import Risk, RiskStatus
from app.models.user import User, UserRole
from app.services import notification_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patch_session_local(monkeypatch, db):
    """Replace SessionLocal inside notification_service with the in-memory db session."""

    class _Factory:
        def __call__(self):
            return _DummySession(db)

    monkeypatch.setattr(notification_service, "SessionLocal", _Factory())


class _DummySession:
    """Wrapper that proxies the in-memory session but no-ops .close()."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, item):
        return getattr(self._real, item)

    def close(self) -> None:
        pass


def _make_user(db, email: str, role: UserRole = UserRole.risk_owner) -> User:
    user = User(
        email=email,
        full_name=email,
        hashed_password=None,
        role=role,
        auth_provider="local",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_risk(db, *, owner: User, created_by: User, human_id: str = "RISK-001") -> Risk:
    risk = Risk(
        risk_id=human_id,
        title=f"Test risk {human_id}",
        description="x",
        owner_id=owner.id,
        created_by_id=created_by.id,
        status=RiskStatus.open,
    )
    db.add(risk)
    db.commit()
    db.refresh(risk)
    return risk


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_create_notification_inserts_row(db):
    user = _make_user(db, "owner@example.com")
    row = notification_service.create_notification(
        db,
        user_id=user.id,
        type=NotificationType.risk_assigned,
        risk_id=None,
        payload={"foo": "bar"},
        link="/risks/RISK-001",
        title="t",
        message="m",
    )
    assert row is not None
    assert row.id is not None
    assert row.read_at is None
    assert row.payload["title"] == "t"
    assert row.payload["message"] == "m"
    assert row.payload["link"] == "/risks/RISK-001"


def test_create_notification_dedup_key_suppresses_duplicate(db):
    user = _make_user(db, "owner@example.com")
    first = notification_service.create_notification(
        db,
        user_id=user.id,
        type=NotificationType.review_overdue,
        risk_id=None,
        payload={},
        link="/risks?due_for_review=true",
        title="t",
        message="m",
        dedup_key="review_overdue:1:2026-05-22",
    )
    second = notification_service.create_notification(
        db,
        user_id=user.id,
        type=NotificationType.review_overdue,
        risk_id=None,
        payload={},
        link="/risks?due_for_review=true",
        title="t2",
        message="m2",
        dedup_key="review_overdue:1:2026-05-22",
    )
    assert first is not None
    assert second is None
    assert db.query(Notification).count() == 1


def test_list_for_user_scopes_to_user(db):
    a = _make_user(db, "a@example.com")
    b = _make_user(db, "b@example.com")
    notification_service.create_notification(
        db, user_id=a.id, type=NotificationType.risk_changed,
        risk_id=None, payload={}, link="/x", title="for a", message="m",
    )
    notification_service.create_notification(
        db, user_id=b.id, type=NotificationType.risk_changed,
        risk_id=None, payload={}, link="/x", title="for b", message="m",
    )
    result = notification_service.list_for_user(db, a.id)
    assert result["total"] == 1
    assert result["unread_total"] == 1
    assert result["items"][0]["title"] == "for a"


def test_unread_count_reflects_mark_read(db):
    user = _make_user(db, "owner@example.com")
    n1 = notification_service.create_notification(
        db, user_id=user.id, type=NotificationType.risk_changed,
        risk_id=None, payload={}, link="/x", title="t", message="m",
    )
    notification_service.create_notification(
        db, user_id=user.id, type=NotificationType.risk_changed,
        risk_id=None, payload={}, link="/x", title="t2", message="m2",
    )
    assert notification_service.unread_count(db, user.id) == 2
    notification_service.mark_read(db, user.id, n1.id)
    assert notification_service.unread_count(db, user.id) == 1


def test_mark_read_is_idempotent(db):
    user = _make_user(db, "owner@example.com")
    n = notification_service.create_notification(
        db, user_id=user.id, type=NotificationType.risk_changed,
        risk_id=None, payload={}, link="/x", title="t", message="m",
    )
    assert notification_service.mark_read(db, user.id, n.id) is True
    assert notification_service.mark_read(db, user.id, n.id) is True
    assert notification_service.unread_count(db, user.id) == 0


def test_mark_read_rejects_other_users_notification(db):
    a = _make_user(db, "a@example.com")
    b = _make_user(db, "b@example.com")
    row = notification_service.create_notification(
        db, user_id=a.id, type=NotificationType.risk_changed,
        risk_id=None, payload={}, link="/x", title="t", message="m",
    )
    assert notification_service.mark_read(db, b.id, row.id) is False


def test_mark_all_read_only_touches_caller_rows(db):
    a = _make_user(db, "a@example.com")
    b = _make_user(db, "b@example.com")
    notification_service.create_notification(
        db, user_id=a.id, type=NotificationType.risk_changed,
        risk_id=None, payload={}, link="/x", title="t", message="m",
    )
    notification_service.create_notification(
        db, user_id=a.id, type=NotificationType.risk_changed,
        risk_id=None, payload={}, link="/x", title="t2", message="m2",
    )
    notification_service.create_notification(
        db, user_id=b.id, type=NotificationType.risk_changed,
        risk_id=None, payload={}, link="/x", title="b1", message="m3",
    )
    marked = notification_service.mark_all_read(db, a.id)
    assert marked == 2
    assert notification_service.unread_count(db, a.id) == 0
    assert notification_service.unread_count(db, b.id) == 1


# ---------------------------------------------------------------------------
# Subscribers
# ---------------------------------------------------------------------------


def test_on_risk_assigned_creates_row_for_new_owner_only(db, patch_session_local):
    actor = _make_user(db, "actor@example.com", role=UserRole.admin)
    new_owner = _make_user(db, "new-owner@example.com")
    prev_owner = _make_user(db, "prev-owner@example.com")
    risk = _make_risk(db, owner=new_owner, created_by=actor, human_id="RISK-007")

    envelope = {
        "id": "evt_test",
        "type": "risk.assigned",
        "subject": {"risk_id": risk.risk_id, "title": risk.title},
        "data": {"new_owner_id": new_owner.id, "previous_owner_id": prev_owner.id},
        "actor": {"id": actor.id, "email": actor.email},
    }
    asyncio.run(notification_service._on_risk_assigned(envelope))

    rows = db.query(Notification).all()
    assert len(rows) == 1
    assert rows[0].user_id == new_owner.id
    assert rows[0].type == NotificationType.risk_assigned
    assert rows[0].risk_id == risk.id


def test_on_risk_assigned_skips_when_actor_is_new_owner(db, patch_session_local):
    user = _make_user(db, "user@example.com")
    risk = _make_risk(db, owner=user, created_by=user, human_id="RISK-100")

    envelope = {
        "id": "evt_test",
        "type": "risk.assigned",
        "subject": {"risk_id": risk.risk_id},
        "data": {"new_owner_id": user.id, "previous_owner_id": None},
        "actor": {"id": user.id, "email": user.email},
    }
    asyncio.run(notification_service._on_risk_assigned(envelope))
    assert db.query(Notification).count() == 0


def test_on_risk_changed_skips_when_actor_is_owner(db, patch_session_local):
    owner = _make_user(db, "owner@example.com")
    risk = _make_risk(db, owner=owner, created_by=owner, human_id="RISK-050")

    envelope = {
        "id": "evt_test",
        "type": "risk.changed",
        "subject": {"risk_id": risk.risk_id},
        "data": {"owner_id": owner.id, "changes": ["status"]},
        "actor": {"id": owner.id, "email": owner.email},
    }
    asyncio.run(notification_service._on_risk_changed(envelope))
    assert db.query(Notification).count() == 0


def test_on_risk_changed_creates_row_when_actor_differs(db, patch_session_local):
    owner = _make_user(db, "owner@example.com")
    actor = _make_user(db, "actor@example.com", role=UserRole.admin)
    risk = _make_risk(db, owner=owner, created_by=actor, human_id="RISK-051")

    envelope = {
        "id": "evt_test",
        "type": "risk.changed",
        "subject": {"risk_id": risk.risk_id},
        "data": {"owner_id": owner.id, "changes": ["status", "score"]},
        "actor": {"id": actor.id, "email": actor.email},
    }
    asyncio.run(notification_service._on_risk_changed(envelope))

    rows = db.query(Notification).all()
    assert len(rows) == 1
    assert rows[0].user_id == owner.id
    assert rows[0].type == NotificationType.risk_changed
    assert "status" in rows[0].payload["changes"]


def test_on_review_overdue_dedupes_by_owner_and_day(db, patch_session_local):
    owner = _make_user(db, "owner@example.com")
    risk = _make_risk(db, owner=owner, created_by=owner, human_id="RISK-200")

    envelope = {
        "id": "evt_test",
        "type": "review.overdue",
        "subject": {"owner_id": owner.id},
        "data": {
            "overdue_risks": [
                {"risk_id": risk.risk_id, "title": risk.title, "next_review_date": "2026-05-01"},
            ]
        },
        "actor": None,
    }
    asyncio.run(notification_service._on_review_overdue(envelope))
    asyncio.run(notification_service._on_review_overdue(envelope))
    assert db.query(Notification).count() == 1


def test_on_response_overdue_creates_row(db, patch_session_local):
    owner = _make_user(db, "owner@example.com")
    risk = _make_risk(db, owner=owner, created_by=owner, human_id="RISK-300")

    envelope = {
        "id": "evt_test",
        "type": "response.overdue",
        "subject": {"risk_id": risk.risk_id, "response_id": 42},
        "data": {
            "owner_id": owner.id,
            "response_type": "mitigate",
            "target_date": "2026-05-01",
        },
        "actor": None,
    }
    asyncio.run(notification_service._on_response_overdue(envelope))
    rows = db.query(Notification).all()
    assert len(rows) == 1
    assert rows[0].type == NotificationType.response_overdue
    assert rows[0].risk_id == risk.id
