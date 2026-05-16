"""Daily-tick scheduler — runs the review-digest + response-overdue jobs once a day.

The loop is an asyncio task started from FastAPI's `lifespan`. Each job is
guarded by an atomic UPDATE on `scheduler_state` so multi-replica deployments
don't double-fire.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.database import SessionLocal
from app.models.risk import Risk, RiskResponse, RiskStatus, ResponseStatus
from app.models.user import User
from app.services import events

logger = logging.getLogger(__name__)

# Tick fires at 09:00 UTC each day. Pick something on a calendar grid so tests
# can reason about it; the exact hour doesn't matter functionally.
TICK_HOUR_UTC = 9


# ---------------------------------------------------------------------------
# Daily logic — split out so it can be exercised by tests and /internal/tick.
# ---------------------------------------------------------------------------


def run_daily_tick(db: Session) -> None:
    """Run the two daily jobs idempotently. Safe to call any number of times per day."""
    today = datetime.now(timezone.utc).date()
    _ensure_state_row(db)
    _run_review_digest(db, today)
    _run_response_overdue(db, today)


def _ensure_state_row(db: Session) -> None:
    """Idempotently seed the singleton row.

    The Alembic migration seeds it, but in-memory SQLite test setups
    (Base.metadata.create_all) skip migrations entirely. This keeps the loop
    safe in both worlds.
    """
    has_row = db.execute(text("SELECT 1 FROM scheduler_state WHERE id = 1")).first()
    if has_row is None:
        db.execute(text("INSERT INTO scheduler_state (id) VALUES (1)"))
        db.commit()


def _run_review_digest(db: Session, today: date) -> None:
    """Emit one review.overdue event per owner with at least one overdue review."""
    result = db.execute(
        text(
            "UPDATE scheduler_state "
            "SET last_review_digest_date = :today "
            "WHERE id = 1 "
            "AND (last_review_digest_date IS NULL OR last_review_digest_date < :today)"
        ),
        {"today": today},
    )
    db.commit()
    if result.rowcount != 1:
        return  # Another replica already won the race today.

    overdue = _overdue_risks(db, today)
    if not overdue:
        return

    # Group by owner so each user gets one consolidated digest.
    by_owner: dict[int, list[Risk]] = {}
    for risk in overdue:
        by_owner.setdefault(risk.owner_id, []).append(risk)

    for owner_id, risks in by_owner.items():
        owner = db.query(User).filter(User.id == owner_id).first()
        if owner is None:
            continue
        events.emit_sync(
            "review.overdue",
            subject={"owner_id": owner.id, "owner_email": owner.email},
            data={
                "overdue_risks": [
                    {
                        "risk_id": r.risk_id,
                        "title": r.title,
                        "next_review_date": (
                            r.next_review_date.isoformat() if r.next_review_date else None
                        ),
                    }
                    for r in risks
                ]
            },
        )


def _run_response_overdue(db: Session, today: date) -> None:
    """Emit one response.overdue event per response that JUST became overdue."""
    result = db.execute(
        text(
            "UPDATE scheduler_state "
            "SET last_response_overdue_date = :today "
            "WHERE id = 1 "
            "AND (last_response_overdue_date IS NULL OR last_response_overdue_date < :today)"
        ),
        {"today": today},
    )
    db.commit()
    if result.rowcount != 1:
        return

    yesterday = today - timedelta(days=1)
    just_overdue = (
        db.query(RiskResponse)
        .filter(RiskResponse.target_date == yesterday)
        .filter(RiskResponse.status != ResponseStatus.completed)
        .all()
    )
    for resp in just_overdue:
        risk = db.query(Risk).filter(Risk.id == resp.risk_id).first()
        if risk is None or risk.deleted_at is not None:
            continue
        owner_id = resp.owner_id or risk.owner_id
        owner = db.query(User).filter(User.id == owner_id).first()
        events.emit_sync(
            "response.overdue",
            subject={
                "risk_id": risk.risk_id,
                "title": risk.title,
                "response_id": resp.id,
            },
            data={
                "owner_id": owner.id if owner else None,
                "owner_email": owner.email if owner else None,
                "target_date": resp.target_date.isoformat() if resp.target_date else None,
                "response_type": resp.response_type.value,
                "status": resp.status.value,
            },
        )


def _overdue_risks(db: Session, today: date) -> list[Risk]:
    """Match the dashboard's 'overdue_reviews' definition."""
    return (
        db.query(Risk)
        .filter(Risk.deleted_at.is_(None))
        .filter(Risk.next_review_date.isnot(None))
        .filter(Risk.next_review_date <= today)
        .filter(Risk.status.notin_([RiskStatus.closed, RiskStatus.mitigated]))
        .all()
    )


# ---------------------------------------------------------------------------
# Loop
# ---------------------------------------------------------------------------


def _seconds_until_next_tick(now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    next_tick = datetime.combine(now.date(), time(TICK_HOUR_UTC, 0, tzinfo=timezone.utc))
    if next_tick <= now:
        next_tick = next_tick + timedelta(days=1)
    return (next_tick - now).total_seconds()


async def daily_tick_loop() -> None:
    """Infinite scheduler loop. Cancelled by the lifespan handler on shutdown."""
    while True:
        try:
            sleep_for = _seconds_until_next_tick()
            await asyncio.sleep(sleep_for)
            db = SessionLocal()
            try:
                run_daily_tick(db)
            finally:
                db.close()
            # Sleep at least 1 hour after a successful tick to avoid hot-looping
            # in case the clock jumps backwards.
            await asyncio.sleep(60 * 60)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("daily_tick_loop iteration failed; retrying in 5 min")
            await asyncio.sleep(5 * 60)
