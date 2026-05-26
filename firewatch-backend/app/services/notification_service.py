"""Per-user notification persistence + event-bus subscribers.

The service writes notification rows in response to events emitted by the rest
of the app. Subscribers register at import time (mirroring webhook_service); the
API layer (app/api/notifications.py) reads and mutates the rows.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.database import SessionLocal
from app.models.notification import Notification, NotificationType
from app.models.risk import Risk
from app.models.user import User
from app.services import events

logger = logging.getLogger(__name__)

__all__ = [
    "create_notification",
    "list_for_user",
    "unread_count",
    "mark_read",
    "mark_all_read",
]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create_notification(
    db: Session,
    *,
    user_id: int,
    type: NotificationType,
    risk_id: int | None,
    payload: dict,
    link: str,
    title: str,
    message: str,
    dedup_key: str | None = None,
) -> Notification | None:
    """Insert a notification row. Returns None if a matching dedup_key already exists."""
    body = dict(payload)
    body.update({"title": title, "message": message, "link": link})
    row = Notification(
        user_id=user_id,
        type=type,
        risk_id=risk_id,
        payload=body,
        dedup_key=dedup_key,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    db.refresh(row)
    return row


def _to_response_dict(row: Notification, risk_human_id: str | None) -> dict:
    payload = row.payload or {}
    return {
        "id": row.id,
        "type": row.type,
        "risk_id": row.risk_id,
        "risk_human_id": risk_human_id,
        "title": payload.get("title", ""),
        "message": payload.get("message", ""),
        "link": payload.get("link", ""),
        "created_at": row.created_at,
        "read_at": row.read_at,
    }


def list_for_user(
    db: Session,
    user_id: int,
    *,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Return {items, total, unread_total} scoped to one user."""
    base = db.query(Notification).filter(Notification.user_id == user_id)
    total = base.count()
    unread_total = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.read_at.is_(None))
        .count()
    )

    query = base
    if unread_only:
        query = query.filter(Notification.read_at.is_(None))

    rows = (
        query.options(joinedload(Notification.risk))
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = [
        _to_response_dict(row, row.risk.risk_id if row.risk is not None else None)
        for row in rows
    ]
    return {"items": items, "total": total, "unread_total": unread_total}


def unread_count(db: Session, user_id: int) -> int:
    return (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.read_at.is_(None))
        .count()
    )


def mark_read(db: Session, user_id: int, notification_id: int) -> bool:
    """Mark a single notification as read. Returns False if not owned by user."""
    row = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user_id)
        .first()
    )
    if row is None:
        return False
    if row.read_at is None:
        row.read_at = datetime.now(timezone.utc)
        db.commit()
    return True


def mark_all_read(db: Session, user_id: int) -> int:
    """Transition every unread row to read. Returns count updated."""
    now = datetime.now(timezone.utc)
    count = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.read_at.is_(None))
        .update({Notification.read_at: now}, synchronize_session=False)
    )
    db.commit()
    return count


# ---------------------------------------------------------------------------
# Event-bus subscribers
# ---------------------------------------------------------------------------


def _get_user(db: Session, user_id: int | None) -> User | None:
    if user_id is None:
        return None
    return db.query(User).filter(User.id == user_id).first()


def _get_risk_by_human_id(db: Session, human_id: str | None) -> Risk | None:
    if not human_id:
        return None
    return db.query(Risk).filter(Risk.risk_id == human_id).first()


def _summarise_titles(titles: list[str], *, head: int = 3) -> str:
    if not titles:
        return ""
    if len(titles) <= head:
        return ", ".join(titles)
    return f"{', '.join(titles[:head])} and {len(titles) - head} more"


async def _on_risk_assigned(envelope: dict) -> None:
    """Notify the new owner of a reassignment."""
    db = SessionLocal()
    try:
        subject = envelope.get("subject") or {}
        data = envelope.get("data") or {}
        actor = envelope.get("actor") or {}
        new_owner_id = data.get("new_owner_id")
        actor_id = actor.get("id")
        human_id = subject.get("risk_id")

        if new_owner_id is None or actor_id == new_owner_id:
            return

        owner = _get_user(db, new_owner_id)
        if owner is None:
            return

        risk = _get_risk_by_human_id(db, human_id)
        if risk is None:
            return

        actor_name = actor.get("email") or "Someone"
        title = f"{risk.risk_id} assigned to you"
        message = f"{actor_name} assigned {risk.risk_id} ('{risk.title}') to you"
        link = f"/risks/{risk.risk_id}"

        create_notification(
            db,
            user_id=owner.id,
            type=NotificationType.risk_assigned,
            risk_id=risk.id,
            payload={
                "actor_id": actor_id,
                "previous_owner_id": data.get("previous_owner_id"),
            },
            link=link,
            title=title,
            message=message,
        )
    except Exception:
        logger.exception("notification subscriber _on_risk_assigned failed")
    finally:
        db.close()


async def _on_review_overdue(envelope: dict) -> None:
    """Aggregate every overdue review for one owner into a single daily digest row."""
    db = SessionLocal()
    try:
        subject = envelope.get("subject") or {}
        data = envelope.get("data") or {}
        owner_id = subject.get("owner_id")
        overdue = data.get("overdue_risks") or []

        if owner_id is None or not overdue:
            return

        owner = _get_user(db, owner_id)
        if owner is None:
            return

        titles = [item.get("risk_id") for item in overdue if item.get("risk_id")]
        count = len(overdue)
        title = f"{count} risk(s) overdue for review"
        message = (
            f"{_summarise_titles(titles)} are overdue for review"
            if titles
            else f"{count} risks are overdue for review"
        )
        link = "/risks?due_for_review=true"
        today = date.today().isoformat()

        create_notification(
            db,
            user_id=owner.id,
            type=NotificationType.review_overdue,
            risk_id=None,
            payload={"overdue": overdue},
            link=link,
            title=title,
            message=message,
            dedup_key=f"review_overdue:{owner.id}:{today}",
        )
    except Exception:
        logger.exception("notification subscriber _on_review_overdue failed")
    finally:
        db.close()


async def _on_response_overdue(envelope: dict) -> None:
    """Notify the risk owner of a freshly-overdue response."""
    db = SessionLocal()
    try:
        subject = envelope.get("subject") or {}
        data = envelope.get("data") or {}
        human_id = subject.get("risk_id")
        response_id = subject.get("response_id")
        owner_id = data.get("owner_id")

        if owner_id is None or response_id is None:
            return

        owner = _get_user(db, owner_id)
        if owner is None:
            return

        risk = _get_risk_by_human_id(db, human_id)
        if risk is None:
            return

        response_type = data.get("response_type") or "response"
        title = f"Response overdue on {risk.risk_id}"
        message = f"{response_type.capitalize()} response on {risk.risk_id} ('{risk.title}') is overdue"
        link = f"/risks/{risk.risk_id}"
        today = date.today().isoformat()

        create_notification(
            db,
            user_id=owner.id,
            type=NotificationType.response_overdue,
            risk_id=risk.id,
            payload={
                "response_id": response_id,
                "response_type": data.get("response_type"),
                "target_date": data.get("target_date"),
            },
            link=link,
            title=title,
            message=message,
            dedup_key=f"response_overdue:{response_id}:{today}",
        )
    except Exception:
        logger.exception("notification subscriber _on_response_overdue failed")
    finally:
        db.close()


async def _on_risk_changed(envelope: dict) -> None:
    """Notify the risk owner that someone else modified their risk."""
    db = SessionLocal()
    try:
        subject = envelope.get("subject") or {}
        data = envelope.get("data") or {}
        actor = envelope.get("actor") or {}
        owner_id = data.get("owner_id")
        actor_id = actor.get("id")
        human_id = subject.get("risk_id")
        changes: list[str] = list(data.get("changes") or [])

        if owner_id is None or actor_id == owner_id or not changes:
            return

        owner = _get_user(db, owner_id)
        if owner is None:
            return

        risk = _get_risk_by_human_id(db, human_id)
        if risk is None:
            return

        actor_name = actor.get("email") or "Someone"
        title = f"{risk.risk_id} updated"
        message = f"{actor_name} updated {', '.join(changes)} on {risk.risk_id}"
        link = f"/risks/{risk.risk_id}"

        create_notification(
            db,
            user_id=owner.id,
            type=NotificationType.risk_changed,
            risk_id=risk.id,
            payload={"actor_id": actor_id, "changes": changes},
            link=link,
            title=title,
            message=message,
        )
    except Exception:
        logger.exception("notification subscriber _on_risk_changed failed")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Event-type → handler dispatcher
# ---------------------------------------------------------------------------


_HANDLERS = {
    "risk.assigned": _on_risk_assigned,
    "review.overdue": _on_review_overdue,
    "response.overdue": _on_response_overdue,
    "risk.changed": _on_risk_changed,
}


async def _dispatch(envelope: dict) -> None:
    """Single subscriber that fans an envelope out to the typed handler."""
    handler = _HANDLERS.get(envelope.get("type"))
    if handler is None:
        return
    await handler(envelope)


# Register with the event bus at import time.
events.subscribe(_dispatch)
