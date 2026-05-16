"""Unit tests for the daily-tick scheduler."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.risk import Risk, RiskResponse, RiskStatus, ResponseStatus, ResponseType
from app.models.scheduler import SchedulerState
from app.models.user import User, UserRole
from app.services import events, scheduler


@pytest.fixture(autouse=True)
def _reset_subscribers():
    original = events.subscribers()
    events.clear_subscribers()
    yield
    events.clear_subscribers()
    for handler in original:
        events.subscribe(handler)


@pytest.fixture
def owner(db) -> User:
    u = User(
        email="owner-sched@example.com",
        full_name="Owner",
        role=UserRole.risk_owner,
        auth_provider="local",
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _capture():
    captured: list[dict] = []

    async def handler(env: dict) -> None:
        captured.append(env)

    return captured, handler


def _make_overdue_risk(db, owner_id: int, *, days_overdue: int = 5) -> Risk:
    risk = Risk(
        risk_id=f"RISK-{owner_id:03d}-OVERDUE-{days_overdue}",
        title="Overdue review",
        owner_id=owner_id,
        created_by_id=owner_id,
        status=RiskStatus.open,
        review_frequency_days=30,
        next_review_date=date.today() - timedelta(days=days_overdue),
    )
    db.add(risk)
    db.commit()
    db.refresh(risk)
    return risk


def _make_response_due_yesterday(db, owner_id: int) -> RiskResponse:
    risk = Risk(
        risk_id=f"RISK-RESP-{owner_id}",
        title="Has response",
        owner_id=owner_id,
        created_by_id=owner_id,
        status=RiskStatus.open,
    )
    db.add(risk)
    db.commit()
    db.refresh(risk)

    resp = RiskResponse(
        risk_id=risk.id,
        response_type=ResponseType.mitigate,
        mitigation_strategy="apply controls",
        owner_id=owner_id,
        target_date=date.today() - timedelta(days=1),
        status=ResponseStatus.in_progress,
    )
    db.add(resp)
    db.commit()
    db.refresh(resp)
    return resp


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_run_daily_tick_is_idempotent(db, owner):
    _make_overdue_risk(db, owner.id)
    _make_response_due_yesterday(db, owner.id)

    captured, handler = _capture()
    events.subscribe(handler)

    scheduler.run_daily_tick(db)
    first_count = len(captured)
    assert first_count >= 1

    scheduler.run_daily_tick(db)
    assert len(captured) == first_count, "second run on same day must emit nothing"


def test_update_guard_marks_state_advanced(db, owner):
    _make_overdue_risk(db, owner.id)
    scheduler.run_daily_tick(db)

    state = db.query(SchedulerState).filter(SchedulerState.id == 1).first()
    assert state is not None
    today = datetime.now(timezone.utc).date()
    assert state.last_review_digest_date == today
    assert state.last_response_overdue_date == today


def test_review_digest_groups_by_owner(db, owner):
    other = User(
        email="other-sched@example.com",
        role=UserRole.risk_owner,
        auth_provider="local",
        is_active=True,
    )
    db.add(other)
    db.commit()
    db.refresh(other)

    _make_overdue_risk(db, owner.id, days_overdue=3)
    _make_overdue_risk(db, owner.id, days_overdue=7)
    _make_overdue_risk(db, other.id, days_overdue=2)

    captured, handler = _capture()
    events.subscribe(handler)
    scheduler.run_daily_tick(db)

    review_events = [c for c in captured if c["type"] == "review.overdue"]
    assert len(review_events) == 2

    owners_seen = {c["subject"]["owner_id"] for c in review_events}
    assert owners_seen == {owner.id, other.id}

    primary = next(c for c in review_events if c["subject"]["owner_id"] == owner.id)
    assert len(primary["data"]["overdue_risks"]) == 2


def test_response_overdue_only_fires_on_first_day_overdue(db, owner):
    """Two responses: one due yesterday (fires), one due 5 days ago (does not)."""
    risk = Risk(
        risk_id="RISK-NEW",
        title="Old response",
        owner_id=owner.id,
        created_by_id=owner.id,
        status=RiskStatus.open,
    )
    db.add(risk)
    db.commit()
    db.refresh(risk)

    db.add(RiskResponse(
        risk_id=risk.id,
        response_type=ResponseType.mitigate,
        mitigation_strategy="long overdue",
        owner_id=owner.id,
        target_date=date.today() - timedelta(days=5),
        status=ResponseStatus.in_progress,
    ))
    _make_response_due_yesterday(db, owner.id)
    db.commit()

    captured, handler = _capture()
    events.subscribe(handler)
    scheduler.run_daily_tick(db)

    response_events = [c for c in captured if c["type"] == "response.overdue"]
    assert len(response_events) == 1


def test_completed_response_does_not_fire(db, owner):
    risk = Risk(
        risk_id="RISK-DONE",
        title="Done risk",
        owner_id=owner.id,
        created_by_id=owner.id,
        status=RiskStatus.open,
    )
    db.add(risk)
    db.commit()
    db.refresh(risk)
    db.add(RiskResponse(
        risk_id=risk.id,
        response_type=ResponseType.mitigate,
        mitigation_strategy="done",
        owner_id=owner.id,
        target_date=date.today() - timedelta(days=1),
        status=ResponseStatus.completed,
    ))
    db.commit()

    captured, handler = _capture()
    events.subscribe(handler)
    scheduler.run_daily_tick(db)
    assert all(c["type"] != "response.overdue" for c in captured)


def test_no_overdue_means_no_events(db, owner):
    captured, handler = _capture()
    events.subscribe(handler)
    scheduler.run_daily_tick(db)
    assert captured == []
