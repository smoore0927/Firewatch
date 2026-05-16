"""Integration tests for /api/internal."""

from __future__ import annotations


def test_tick_runs_for_admin(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.post("/api/internal/tick")
    assert resp.status_code == 200
    assert resp.json() == {"ran": True}


def test_tick_forbidden_for_analyst(client, analyst_user, login_as):
    login_as(analyst_user)
    resp = client.post("/api/internal/tick")
    assert resp.status_code == 403


def test_tick_forbidden_for_owner(client, owner_user, login_as):
    login_as(owner_user)
    resp = client.post("/api/internal/tick")
    assert resp.status_code == 403


def test_tick_requires_auth(client):
    resp = client.post("/api/internal/tick")
    assert resp.status_code == 401
