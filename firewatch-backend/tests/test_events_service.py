"""Unit tests for the in-process event bus."""

from __future__ import annotations

import asyncio

import pytest

from app.services import events


@pytest.fixture(autouse=True)
def _reset_subscribers():
    """Snapshot/restore the subscribers list between tests."""
    original = events.subscribers()
    events.clear_subscribers()
    yield
    events.clear_subscribers()
    for handler in original:
        events.subscribe(handler)


def test_emit_invokes_every_subscriber():
    calls: list[dict] = []

    async def handler_a(env: dict) -> None:
        calls.append(("a", env))

    async def handler_b(env: dict) -> None:
        calls.append(("b", env))

    events.subscribe(handler_a)
    events.subscribe(handler_b)

    async def run() -> None:
        await events.emit(
            "risk.assigned",
            subject={"risk_id": "RISK-001"},
            data={"new_owner_id": 5},
            actor={"id": 1, "email": "a@example.com"},
        )
        # Yield so the scheduled tasks actually run.
        await asyncio.sleep(0)

    asyncio.run(run())

    seen_handlers = {c[0] for c in calls}
    assert seen_handlers == {"a", "b"}
    envelope = calls[0][1]
    assert envelope["type"] == "risk.assigned"
    assert envelope["subject"] == {"risk_id": "RISK-001"}
    assert envelope["data"] == {"new_owner_id": 5}
    assert envelope["actor"] == {"id": 1, "email": "a@example.com"}
    assert envelope["id"].startswith("evt_")
    assert "occurred_at" in envelope


def test_one_bad_subscriber_does_not_break_others():
    survivors: list[str] = []

    async def bad(env: dict) -> None:
        raise RuntimeError("kaboom")

    async def good(env: dict) -> None:
        survivors.append(env["id"])

    events.subscribe(bad)
    events.subscribe(good)

    async def run() -> None:
        await events.emit(
            "firewatch.test",
            subject={},
            data={},
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(run())
    assert len(survivors) == 1


def test_emit_sync_dispatches_to_subscribers():
    """emit_sync from non-async context still runs subscribers."""
    seen: list[dict] = []

    async def handler(env: dict) -> None:
        seen.append(env)

    events.subscribe(handler)

    events.emit_sync(
        "review.overdue",
        subject={"owner_id": 7},
        data={"overdue_risks": []},
    )

    assert len(seen) == 1
    assert seen[0]["type"] == "review.overdue"
