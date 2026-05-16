"""Unit tests for the webhook delivery service."""

from __future__ import annotations

import asyncio
import hmac
import json
from hashlib import sha256
from typing import Any

import httpx
import pytest

from app.core.crypto import decrypt_from_storage
from app.models.user import User, UserRole
from app.models.webhook import DeliveryStatus, WebhookDelivery, WebhookSubscription
from app.services import webhook_service
from app.services.webhook_service import sign_body


@pytest.fixture
def admin_row(db) -> User:
    user = User(
        email="webhooks-admin@example.com",
        full_name="Admin",
        hashed_password=None,
        role=UserRole.admin,
        auth_provider="local",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def patch_session_local(monkeypatch, db):
    """Replace SessionLocal with a factory that yields the in-memory db session.

    The delivery code uses `SessionLocal()` directly (not Depends-injected),
    so we have to swap the factory itself.
    """

    class _Factory:
        def __call__(self):
            return _DummySession(db)

    monkeypatch.setattr(webhook_service, "SessionLocal", _Factory())


class _DummySession:
    """A wrapper that proxies to the shared session but no-ops on .close().

    The delivery code opens its own session and closes it; the test wants to
    keep the session alive across the test body."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, item):
        return getattr(self._real, item)

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Helpers to capture httpx.AsyncClient.post calls
# ---------------------------------------------------------------------------


class _RecordedRequest:
    def __init__(self, url: str, content: bytes, headers: dict):
        self.url = url
        self.content = content
        self.headers = headers


def _install_httpx_mock(monkeypatch, *, responses: list[Any]) -> list[_RecordedRequest]:
    """Patch httpx.AsyncClient.post to return scripted responses and record calls.

    `responses` may contain either integer status codes (used as the status of
    a 200 OK body) or Exception instances (raised instead of returning).
    """
    recorded: list[_RecordedRequest] = []
    response_iter = iter(responses)

    async def fake_post(self, url, *, content, headers, **kwargs):
        recorded.append(_RecordedRequest(url=url, content=content, headers=dict(headers)))
        try:
            nxt = next(response_iter)
        except StopIteration:
            nxt = 200
        if isinstance(nxt, Exception):
            raise nxt
        return httpx.Response(status_code=nxt, content=b"ok")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return recorded


# ---------------------------------------------------------------------------
# sign_body / generate_secret
# ---------------------------------------------------------------------------


def test_sign_body_matches_manual_hmac():
    body = b'{"hello":"world"}'
    timestamp = 1_700_000_000
    secret = "supersecret"

    signed = sign_body(secret, timestamp=timestamp, body=body)
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}.{body.decode('utf-8')}".encode("utf-8"),
        sha256,
    ).hexdigest()
    assert signed == expected


def test_generate_secret_returns_random_url_safe_token():
    plaintext = webhook_service.generate_secret()
    assert isinstance(plaintext, str)
    assert len(plaintext) >= 32
    # Two calls should produce different values.
    assert plaintext != webhook_service.generate_secret()


def test_create_stores_encrypted_not_plaintext(db, admin_row):
    sub, plaintext = webhook_service.create(
        db,
        name="enc",
        target_url="https://example.invalid/hook",
        event_types=["firewatch.test"],
        created_by=admin_row.id,
    )
    # Column holds ciphertext, NOT the plaintext returned to the caller.
    assert sub.secret != plaintext
    # Round-trips back to the plaintext via the crypto helper.
    assert decrypt_from_storage(sub.secret) == plaintext


# ---------------------------------------------------------------------------
# Delivery happy path
# ---------------------------------------------------------------------------


def test_successful_delivery_sets_status_and_resets_failures(
    db, admin_row, patch_session_local, monkeypatch
):
    sub, plaintext = webhook_service.create(
        db,
        name="happy",
        target_url="https://example.invalid/hook",
        event_types=["firewatch.test"],
        created_by=admin_row.id,
    )
    sub.consecutive_failures = 7  # was failing previously
    db.commit()

    recorded = _install_httpx_mock(monkeypatch, responses=[200])

    asyncio.run(_run_delivery(sub))

    db.expire_all()
    delivery = (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.subscription_id == sub.id)
        .first()
    )
    assert delivery is not None
    assert delivery.status == DeliveryStatus.success
    assert delivery.attempt_count == 1
    assert delivery.http_status == 200
    assert delivery.completed_at is not None

    sub_reloaded = db.query(WebhookSubscription).filter(WebhookSubscription.id == sub.id).first()
    assert sub_reloaded.consecutive_failures == 0
    assert sub_reloaded.last_delivered_at is not None

    # HMAC and timestamp headers are present.
    assert len(recorded) == 1
    req = recorded[0]
    assert "X-Firewatch-Signature" in req.headers
    assert req.headers["X-Firewatch-Signature"].startswith("sha256=")
    assert req.headers["X-Firewatch-Event"] == "firewatch.test"
    assert req.headers["X-Firewatch-Timestamp"].isdigit()

    # The signature must match a hand-computed HMAC over `${ts}.${body}`.
    timestamp = int(req.headers["X-Firewatch-Timestamp"])
    expected = hmac.new(
        plaintext.encode("utf-8"),
        f"{timestamp}.{req.content.decode('utf-8')}".encode("utf-8"),
        sha256,
    ).hexdigest()
    assert req.headers["X-Firewatch-Signature"] == f"sha256={expected}"


# ---------------------------------------------------------------------------
# Failure path
# ---------------------------------------------------------------------------


def test_failed_delivery_increments_consecutive_failures(
    db, admin_row, patch_session_local, monkeypatch
):
    # Skip the backoff sleeps so the test runs in milliseconds.
    monkeypatch.setattr(webhook_service, "RETRY_BACKOFF", [0, 0, 0])

    sub, _ = webhook_service.create(
        db,
        name="sad",
        target_url="https://example.invalid/hook",
        event_types=["firewatch.test"],
        created_by=admin_row.id,
    )

    _install_httpx_mock(monkeypatch, responses=[500, 502, 503])

    asyncio.run(_run_delivery(sub))

    db.expire_all()
    delivery = (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.subscription_id == sub.id)
        .first()
    )
    assert delivery.status == DeliveryStatus.failed
    assert delivery.attempt_count == webhook_service.MAX_ATTEMPTS
    assert delivery.http_status in (500, 502, 503)
    assert delivery.completed_at is not None
    assert delivery.error is not None

    sub_reloaded = db.query(WebhookSubscription).filter(WebhookSubscription.id == sub.id).first()
    assert sub_reloaded.consecutive_failures == 1


def test_success_after_retry_marks_success(
    db, admin_row, patch_session_local, monkeypatch
):
    monkeypatch.setattr(webhook_service, "RETRY_BACKOFF", [0, 0, 0])

    sub, _ = webhook_service.create(
        db,
        name="eventually",
        target_url="https://example.invalid/hook",
        event_types=["firewatch.test"],
        created_by=admin_row.id,
    )

    _install_httpx_mock(monkeypatch, responses=[500, 200])

    asyncio.run(_run_delivery(sub))

    db.expire_all()
    delivery = (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.subscription_id == sub.id)
        .first()
    )
    assert delivery.status == DeliveryStatus.success
    assert delivery.attempt_count == 2
    assert delivery.http_status == 200


def test_backoff_constant_matches_brief():
    """Sanity-check the documented schedule (1s, 5s, 25s)."""
    assert webhook_service.RETRY_BACKOFF == [1, 5, 25]
    assert webhook_service.MAX_ATTEMPTS == 3


def test_response_body_and_error_are_truncated(
    db, admin_row, patch_session_local, monkeypatch
):
    monkeypatch.setattr(webhook_service, "RETRY_BACKOFF", [0, 0, 0])

    sub, _ = webhook_service.create(
        db,
        name="oversize",
        target_url="https://example.invalid/hook",
        event_types=["firewatch.test"],
        created_by=admin_row.id,
    )

    large = "x" * 5000

    async def fake_post(self, url, *, content, headers, **kwargs):
        return httpx.Response(status_code=500, content=large.encode("utf-8"))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    asyncio.run(_run_delivery(sub))

    db.expire_all()
    delivery = (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.subscription_id == sub.id)
        .first()
    )
    assert delivery.response_body is not None
    assert len(delivery.response_body) <= webhook_service.MAX_BODY_LEN


# ---------------------------------------------------------------------------
# Subscription filtering
# ---------------------------------------------------------------------------


def test_deliver_skips_inactive_or_unsubscribed(
    db, admin_row, patch_session_local, monkeypatch
):
    monkeypatch.setattr(webhook_service, "RETRY_BACKOFF", [0, 0, 0])

    active, _ = webhook_service.create(
        db,
        name="active-matching",
        target_url="https://example.invalid/a",
        event_types=["risk.assigned"],
        created_by=admin_row.id,
    )
    inactive, _ = webhook_service.create(
        db,
        name="inactive-matching",
        target_url="https://example.invalid/b",
        event_types=["risk.assigned"],
        created_by=admin_row.id,
    )
    inactive.is_active = False
    other, _ = webhook_service.create(
        db,
        name="wrong-type",
        target_url="https://example.invalid/c",
        event_types=["review.overdue"],
        created_by=admin_row.id,
    )
    db.commit()

    recorded = _install_httpx_mock(monkeypatch, responses=[200])

    envelope = {
        "id": "evt_test",
        "type": "risk.assigned",
        "occurred_at": "2026-05-15T00:00:00+00:00",
        "actor": None,
        "subject": {},
        "data": {},
    }

    async def run() -> None:
        await webhook_service.deliver(envelope)
        # let scheduled tasks complete
        for _ in range(5):
            await asyncio.sleep(0)

    asyncio.run(run())

    db.expire_all()
    deliveries = db.query(WebhookDelivery).all()
    assert len(deliveries) == 1
    assert deliveries[0].subscription_id == active.id


# ---------------------------------------------------------------------------
# Helper: run a single subscription end-to-end via deliver()
# ---------------------------------------------------------------------------


async def _run_delivery(sub: WebhookSubscription) -> None:
    envelope = {
        "id": "evt_test_abc",
        "type": "firewatch.test",
        "occurred_at": "2026-05-15T00:00:00+00:00",
        "actor": None,
        "subject": {"subscription_id": sub.id},
        "data": {"hello": "world"},
    }
    await webhook_service.deliver(envelope)
    # Give the spawned _post_with_retry tasks time to finish.
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
