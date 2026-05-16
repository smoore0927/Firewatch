"""Tiny in-process pub/sub event bus.

Producers call `emit(...)` (or `emit_sync(...)` from sync code paths) to publish an
event envelope to every registered subscriber. Subscribers are coroutines that
accept the envelope dict. They are invoked via `asyncio.create_task`, so a slow
or broken subscriber never blocks the producing request.

The only subscriber in v1 is the webhook dispatcher; adding e.g. an SMTP/email
subscriber later is a new file that calls `events.subscribe(handler)` at import time.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict], Awaitable[None]]

_subscribers: list[EventHandler] = []


def subscribe(handler: EventHandler) -> None:
    """Register a handler. Idempotent — re-registering is a no-op."""
    if handler not in _subscribers:
        _subscribers.append(handler)


def clear_subscribers() -> None:
    """Test-only helper to reset the subscriber list."""
    _subscribers.clear()


def subscribers() -> list[EventHandler]:
    """Return a copy of the subscriber list (mostly for introspection in tests)."""
    return list(_subscribers)


def _build_envelope(
    event_type: str,
    *,
    subject: dict,
    data: dict,
    actor: dict | None,
) -> dict:
    return {
        "id": f"evt_{uuid.uuid4().hex}",
        "type": event_type,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "subject": subject,
        "data": data,
    }


async def _safe_call(handler: EventHandler, envelope: dict) -> None:
    """Wrap a subscriber call so one bad subscriber can't take down others."""
    try:
        await handler(envelope)
    except Exception:
        logger.exception("Event subscriber %r failed for event %s", handler, envelope.get("id"))


async def emit(
    event_type: str,
    *,
    subject: dict,
    data: dict,
    actor: dict | None = None,
) -> dict:
    """Publish an event from an async context. Returns the envelope for tests."""
    envelope = _build_envelope(event_type, subject=subject, data=data, actor=actor)
    for handler in list(_subscribers):
        asyncio.create_task(_safe_call(handler, envelope))
    return envelope


def emit_sync(
    event_type: str,
    *,
    subject: dict,
    data: dict,
    actor: dict | None = None,
) -> dict:
    """Schedule an emit from synchronous code (e.g. inside a sync service method).

    If a running event loop exists in the current thread (FastAPI request path),
    we hand the coroutine off via `create_task`. Otherwise — typically scripts,
    Alembic, or background threads — we run it inline with `asyncio.run` so the
    caller still gets the same fire-and-forget semantics. Returns the envelope.
    """
    envelope = _build_envelope(event_type, subject=subject, data=data, actor=actor)
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None

    async def _dispatch() -> None:
        for handler in list(_subscribers):
            asyncio.create_task(_safe_call(handler, envelope))

    if loop is not None and loop.is_running():
        loop.create_task(_dispatch())
    else:
        # No running loop — synthesise one so subscribers still run.
        try:
            asyncio.run(_dispatch())
        except RuntimeError:
            logger.exception("Could not dispatch event %s synchronously", envelope["id"])
    return envelope
