"""Webhook CRUD + asynchronous delivery with retry.

Delivery flow:
  events.emit(...)                       (producer)
    -> deliver(envelope)                 (subscribed at import time)
       -> writes WebhookDelivery row(s)
       -> asyncio.create_task(_post_with_retry(...))
          -> up to 3 attempts, exponential backoff (1s, 5s, 25s)
          -> persists every attempt (status, http_status, error, completed_at)
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import secrets
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_from_storage, encrypt_for_storage
from app.core.url_safety import validate_outbound_url
from app.models.database import SessionLocal
from app.models.webhook import DeliveryStatus, WebhookDelivery, WebhookSubscription
from app.services import events

logger = logging.getLogger(__name__)

# Total HTTP timeout for a single delivery attempt.
HTTP_TIMEOUT_SECONDS = 10.0
# Backoff schedule (seconds) before attempts 2 and 3.
RETRY_BACKOFF = [1, 5, 25]
MAX_ATTEMPTS = 3
# Storage caps for free-form fields.
MAX_BODY_LEN = 1024
MAX_ERROR_LEN = 1024


# ---------------------------------------------------------------------------
# Secret + signing
# ---------------------------------------------------------------------------


def generate_secret() -> str:
    """Return a URL-safe random HMAC secret (plaintext)."""
    return secrets.token_urlsafe(32)


def sign_body(secret: str, *, timestamp: int, body: bytes) -> str:
    """HMAC-sha256 hex digest of `f"{timestamp}.{body}"` using the plaintext secret."""
    mac = hmac.new(secret.encode("utf-8"), f"{timestamp}.{body.decode('utf-8')}".encode("utf-8"), sha256)
    return mac.hexdigest()


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return value[:limit]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create(
    db: Session,
    *,
    name: str,
    target_url: str,
    event_types: list[str],
    created_by: int,
) -> tuple[WebhookSubscription, str]:
    """Persist a new subscription and return (row, plaintext_secret)."""
    plaintext = generate_secret()
    row = WebhookSubscription(
        name=name,
        target_url=target_url,
        event_types=list(event_types),
        secret=encrypt_for_storage(plaintext),
        created_by_id=created_by,
        is_active=True,
        consecutive_failures=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, plaintext


def list_all(db: Session) -> list[WebhookSubscription]:
    return (
        db.query(WebhookSubscription)
        .order_by(WebhookSubscription.created_at.desc())
        .all()
    )


def get(db: Session, sub_id: int) -> WebhookSubscription:
    sub = db.query(WebhookSubscription).filter(WebhookSubscription.id == sub_id).first()
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Webhook subscription not found"
        )
    return sub


def update(
    db: Session,
    sub: WebhookSubscription,
    *,
    name: str | None = None,
    target_url: str | None = None,
    event_types: list[str] | None = None,
    is_active: bool | None = None,
) -> WebhookSubscription:
    if name is not None:
        sub.name = name
    if target_url is not None:
        sub.target_url = target_url
    if event_types is not None:
        sub.event_types = list(event_types)
    if is_active is not None:
        sub.is_active = is_active
    db.commit()
    db.refresh(sub)
    return sub


def delete(db: Session, sub: WebhookSubscription) -> None:
    db.delete(sub)
    db.commit()


def list_deliveries(db: Session, sub_id: int, *, skip: int = 0, limit: int = 50) -> dict:
    # Touch the parent to 404 cleanly on bad sub_id.
    get(db, sub_id)
    base = (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.subscription_id == sub_id)
    )
    total = base.count()
    items = (
        base.order_by(WebhookDelivery.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return {"total": total, "items": items}


# ---------------------------------------------------------------------------
# Delivery (event-bus subscriber + retry loop)
# ---------------------------------------------------------------------------


async def deliver(envelope: dict) -> None:
    """Event-bus subscriber: fan out one envelope to every matching subscription."""
    event_type = envelope.get("type")
    if not event_type:
        return

    db = SessionLocal()
    try:
        subs = (
            db.query(WebhookSubscription)
            .filter(WebhookSubscription.is_active.is_(True))
            .all()
        )
        targets = [s for s in subs if _matches(s.event_types, event_type)]
        if not targets:
            return

        payload_json = json.dumps(envelope, sort_keys=True)
        delivery_ids: list[int] = []
        for sub in targets:
            row = WebhookDelivery(
                subscription_id=sub.id,
                event_id=envelope["id"],
                event_type=event_type,
                payload_json=payload_json,
                status=DeliveryStatus.pending,
                attempt_count=0,
            )
            db.add(row)
            db.flush()
            delivery_ids.append(row.id)
        db.commit()
    finally:
        db.close()

    for delivery_id in delivery_ids:
        asyncio.create_task(_post_with_retry(delivery_id))


def _matches(stored_types: Any, event_type: str) -> bool:
    """Return True if `event_type` is in the JSON-stored list on the subscription."""
    if not stored_types:
        return False
    if isinstance(stored_types, str):
        # Defensive: some drivers may return raw JSON text.
        try:
            stored_types = json.loads(stored_types)
        except ValueError:
            return False
    return event_type in stored_types


async def _post_with_retry(delivery_id: int) -> None:
    """Drive a single delivery through up to MAX_ATTEMPTS attempts."""
    for attempt_index in range(MAX_ATTEMPTS):
        if attempt_index > 0:
            await asyncio.sleep(RETRY_BACKOFF[attempt_index])

        succeeded, terminal = await _attempt_once(delivery_id, attempt_index + 1)
        if succeeded or terminal:
            return


async def _attempt_once(delivery_id: int, attempt_number: int) -> tuple[bool, bool]:
    """Run a single POST attempt. Returns (succeeded, terminal).

    `terminal` is True if no further retry should run (success, or final failed
    attempt). A short-circuit return path is the only place where we return
    (False, False) — i.e. retry."""
    db = SessionLocal()
    try:
        delivery = (
            db.query(WebhookDelivery).filter(WebhookDelivery.id == delivery_id).first()
        )
        if delivery is None:
            return False, True
        sub = (
            db.query(WebhookSubscription)
            .filter(WebhookSubscription.id == delivery.subscription_id)
            .first()
        )
        if sub is None:
            return False, True

        # DNS-rebinding defense: re-validate the target URL right before each
        # POST and pin the resolved IP. A previously-public host could now
        # resolve to a private IP.
        try:
            target = validate_outbound_url(sub.target_url)
        except ValueError as exc:
            delivery.attempt_count = attempt_number
            delivery.status = DeliveryStatus.failed
            delivery.error = _truncate(str(exc), MAX_ERROR_LEN)
            delivery.completed_at = datetime.now(timezone.utc)
            sub.consecutive_failures = (sub.consecutive_failures or 0) + 1
            db.commit()
            return False, True

        secret = decrypt_from_storage(sub.secret)
        body_bytes = delivery.payload_json.encode("utf-8")
        timestamp = int(datetime.now(timezone.utc).timestamp())
        signature = sign_body(secret, timestamp=timestamp, body=body_bytes)
        headers = {
            "Content-Type": "application/json",
            "X-Firewatch-Event": delivery.event_type,
            "X-Firewatch-Timestamp": str(timestamp),
            "X-Firewatch-Signature": f"sha256={signature}",
        }

        scheme = target.parsed.scheme
        hostname = target.parsed.hostname
        path = target.parsed.path or "/"
        query = f"?{target.parsed.query}" if target.parsed.query else ""

        if target.pinned_ip is not None:
            ip = target.pinned_ip
            ip_literal = f"[{ip}]" if ":" in ip else ip
            connect_url = f"{scheme}://{ip_literal}:{target.pinned_port}{path}{query}"
            request_headers = {**headers, "Host": hostname}
            extensions = {"sni_hostname": hostname}
        else:
            connect_url = sub.target_url
            request_headers = headers
            extensions = {}

        delivery.attempt_count = attempt_number
        db.commit()

        http_status: int | None = None
        response_text: str | None = None
        error: str | None = None
        ok = False
        try:
            async with httpx.AsyncClient(
                timeout=HTTP_TIMEOUT_SECONDS, follow_redirects=False
            ) as client:
                resp = await client.post(
                    connect_url,
                    content=body_bytes,
                    headers=request_headers,
                    extensions=extensions,
                )
            http_status = resp.status_code
            response_text = resp.text
            if 200 <= resp.status_code < 300:
                ok = True
            elif 300 <= resp.status_code < 400:
                error = f"unexpected redirect (HTTP {resp.status_code}); redirects are not followed"
            else:
                error = f"non-2xx status {resp.status_code}"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

        # Reload delivery — we held the row through the network call which can
        # be slow; refresh to make sure we're not stomping on concurrent writes.
        delivery = (
            db.query(WebhookDelivery).filter(WebhookDelivery.id == delivery_id).first()
        )
        sub = (
            db.query(WebhookSubscription)
            .filter(WebhookSubscription.id == delivery.subscription_id)
            .first()
        )
        delivery.http_status = http_status
        delivery.response_body = _truncate(response_text, MAX_BODY_LEN)
        delivery.error = _truncate(error, MAX_ERROR_LEN)

        if ok:
            delivery.status = DeliveryStatus.success
            delivery.completed_at = datetime.now(timezone.utc)
            sub.last_delivered_at = delivery.completed_at
            sub.consecutive_failures = 0
            db.commit()
            return True, True

        # Failed attempt.
        if attempt_number >= MAX_ATTEMPTS:
            delivery.status = DeliveryStatus.failed
            delivery.completed_at = datetime.now(timezone.utc)
            sub.consecutive_failures = (sub.consecutive_failures or 0) + 1
            db.commit()
            return False, True

        # Schedule next attempt — leave row in `pending`.
        next_in = RETRY_BACKOFF[attempt_number]
        delivery.scheduled_for = datetime.now(timezone.utc)
        db.commit()
        return False, False
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Synthetic test fire (used by POST /webhooks/{id}/test)
# ---------------------------------------------------------------------------


async def fire_test_event(db: Session, sub: WebhookSubscription) -> int:
    """Send one firewatch.test envelope to a single subscription. Returns delivery_id."""
    validate_outbound_url(sub.target_url)
    envelope = {
        "id": f"evt_test_{secrets.token_hex(8)}",
        "type": "firewatch.test",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "actor": None,
        "subject": {"subscription_id": sub.id},
        "data": {"message": "Firewatch webhook connectivity test"},
    }
    payload_json = json.dumps(envelope, sort_keys=True)
    delivery = WebhookDelivery(
        subscription_id=sub.id,
        event_id=envelope["id"],
        event_type=envelope["type"],
        payload_json=payload_json,
        status=DeliveryStatus.pending,
        attempt_count=0,
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    asyncio.create_task(_post_with_retry(delivery.id))
    return delivery.id


# Register with the event bus at import time. Importing this module from
# `main.py` is sufficient to wire the subscriber.
events.subscribe(deliver)
