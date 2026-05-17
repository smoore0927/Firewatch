"""Integration tests for /api/webhooks."""

from __future__ import annotations

import json
import socket

import pytest

from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.webhook import WebhookSubscription


def _create(client, **overrides) -> dict:
    payload = {
        "name": "test-sub",
        "target_url": "https://example.invalid/hook",
        "event_types": ["risk.assigned"],
    }
    payload.update(overrides)
    resp = client.post("/api/webhooks", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Auth / permissions
# ---------------------------------------------------------------------------


def test_admin_can_create_subscription(client, admin_user, login_as):
    login_as(admin_user)
    body = _create(client)
    assert body["name"] == "test-sub"
    assert body["is_active"] is True
    assert "secret" in body
    assert body["secret"]
    assert body["created_by_id"] == admin_user.id


def test_non_admin_cannot_list_subscriptions(client, analyst_user, login_as):
    login_as(analyst_user)
    resp = client.get("/api/webhooks")
    assert resp.status_code == 403


def test_non_admin_cannot_create_subscription(client, owner_user, login_as):
    login_as(owner_user)
    resp = client.post(
        "/api/webhooks",
        json={
            "name": "x",
            "target_url": "https://example.invalid/hook",
            "event_types": ["firewatch.test"],
        },
    )
    assert resp.status_code == 403


def test_unauthenticated_returns_401(client):
    resp = client.get("/api/webhooks")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Secret exposure rules
# ---------------------------------------------------------------------------


def test_secret_is_only_returned_on_create(client, admin_user, login_as):
    login_as(admin_user)
    created = _create(client)
    sub_id = created["id"]
    plaintext = created["secret"]

    # GET single
    single = client.get(f"/api/webhooks/{sub_id}").json()
    assert "secret" not in single
    assert "secret_hash" not in single

    # GET list
    listed = client.get("/api/webhooks").json()
    for row in listed:
        assert "secret" not in row
        assert "secret_hash" not in row

    # The plaintext is not stored anywhere in the GET responses.
    assert plaintext not in json.dumps(listed)


def test_stored_secret_is_ciphertext_not_plaintext(client, admin_user, login_as, db):
    """The DB column holds Fernet ciphertext; the API never surfaces it."""
    from app.core.crypto import decrypt_from_storage

    login_as(admin_user)
    created = _create(client)
    plaintext = created["secret"]

    db_row = db.query(WebhookSubscription).filter(WebhookSubscription.id == created["id"]).first()
    # Stored value is NOT the plaintext...
    assert db_row.secret != plaintext
    # ...but decrypts back to it.
    assert decrypt_from_storage(db_row.secret) == plaintext
    # The ciphertext itself must never appear in API responses.
    assert "secret_hash" not in created
    listed = client.get("/api/webhooks").json()
    assert db_row.secret not in json.dumps(listed)
    single = client.get(f"/api/webhooks/{created['id']}").json()
    assert db_row.secret not in json.dumps(single)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_unknown_event_type_is_rejected(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.post(
        "/api/webhooks",
        json={
            "name": "bad",
            "target_url": "https://example.invalid/hook",
            "event_types": ["not.a.real.event"],
        },
    )
    assert resp.status_code == 422


def test_invalid_target_url_is_rejected(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.post(
        "/api/webhooks",
        json={
            "name": "bad",
            "target_url": "not a url",
            "event_types": ["firewatch.test"],
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Update + delete
# ---------------------------------------------------------------------------


def test_patch_updates_fields(client, admin_user, login_as):
    login_as(admin_user)
    created = _create(client)
    resp = client.patch(
        f"/api/webhooks/{created['id']}",
        json={"name": "renamed", "is_active": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "renamed"
    assert body["is_active"] is False


def test_delete_removes_subscription(client, admin_user, login_as):
    login_as(admin_user)
    created = _create(client)
    resp = client.delete(f"/api/webhooks/{created['id']}")
    assert resp.status_code == 204
    resp = client.get(f"/api/webhooks/{created['id']}")
    assert resp.status_code == 404


def test_get_unknown_subscription_returns_404(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.get("/api/webhooks/99999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


def _latest_audit(db, *, action: str) -> AuditLog | None:
    return (
        db.query(AuditLog)
        .filter(AuditLog.action == action)
        .order_by(AuditLog.id.desc())
        .first()
    )


def test_create_audit_event_does_not_include_secret(client, admin_user, login_as, db):
    login_as(admin_user)
    created = _create(client)
    row = _latest_audit(db, action="webhook.created")
    assert row is not None
    assert row.resource_id == str(created["id"])
    assert created["secret"] not in (row.details or "")


def test_update_audit_event_recorded(client, admin_user, login_as, db):
    login_as(admin_user)
    created = _create(client)
    client.patch(f"/api/webhooks/{created['id']}", json={"is_active": False})
    row = _latest_audit(db, action="webhook.updated")
    assert row is not None
    details = json.loads(row.details)
    assert details.get("is_active") is False


def test_delete_audit_event_recorded(client, admin_user, login_as, db):
    login_as(admin_user)
    created = _create(client)
    client.delete(f"/api/webhooks/{created['id']}")
    row = _latest_audit(db, action="webhook.deleted")
    assert row is not None
    assert row.resource_id == str(created["id"])


# ---------------------------------------------------------------------------
# Deliveries endpoint
# ---------------------------------------------------------------------------


def test_deliveries_endpoint_returns_empty_for_new_subscription(
    client, admin_user, login_as
):
    login_as(admin_user)
    created = _create(client)
    resp = client.get(f"/api/webhooks/{created['id']}/deliveries")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"total": 0, "items": []}


# ---------------------------------------------------------------------------
# SSRF / outbound URL safety
# ---------------------------------------------------------------------------


def _addrinfo(addr: str, family: int = socket.AF_INET) -> list[tuple]:
    """Build a getaddrinfo return value containing a single address."""
    sockaddr = (addr, 0) if family == socket.AF_INET else (addr, 0, 0, 0)
    return [(family, socket.SOCK_STREAM, 0, "", sockaddr)]


def _public_dns(monkeypatch) -> None:
    """Pretend every hostname resolves to a globally-routable IP (8.8.8.8)."""
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: _addrinfo("8.8.8.8"))


def _enter_prod(monkeypatch) -> None:
    """Flip DEBUG off AFTER login has happened (login needs Secure-cookie-friendly mode)."""
    monkeypatch.setattr(settings, "DEBUG", False)


def test_create_rejects_http_in_prod(client, admin_user, login_as, monkeypatch):
    login_as(admin_user)
    _enter_prod(monkeypatch)
    _public_dns(monkeypatch)
    resp = client.post(
        "/api/webhooks",
        json={
            "name": "insecure",
            "target_url": "http://example.com/hook",
            "event_types": ["firewatch.test"],
        },
    )
    assert resp.status_code == 422
    assert "non-HTTPS" in resp.json()["detail"]


def test_create_accepts_http_in_debug(client, admin_user, login_as):
    # The .env / conftest default is DEBUG=True; no flip required.
    login_as(admin_user)
    resp = client.post(
        "/api/webhooks",
        json={
            "name": "dev",
            "target_url": "http://localhost:8000/hook",
            "event_types": ["firewatch.test"],
        },
    )
    assert resp.status_code == 201


@pytest.mark.parametrize(
    "addr,family",
    [
        ("127.0.0.1", socket.AF_INET),
        ("10.0.0.5", socket.AF_INET),
        ("169.254.169.254", socket.AF_INET),
        ("::1", socket.AF_INET6),
    ],
)
def test_create_rejects_internal_resolution_in_prod(
    client, admin_user, login_as, monkeypatch, addr, family
):
    login_as(admin_user)
    _enter_prod(monkeypatch)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: _addrinfo(addr, family))
    resp = client.post(
        "/api/webhooks",
        json={
            "name": "ssrf",
            "target_url": "https://attacker.example.com/hook",
            "event_types": ["firewatch.test"],
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "private/internal IP" in detail
    assert addr in detail


@pytest.mark.parametrize("addr", ["127.0.0.1", "10.0.0.5", "169.254.169.254"])
def test_create_accepts_internal_resolution_in_debug(
    client, admin_user, login_as, monkeypatch, addr
):
    # DEBUG defaults to True via .env; no DNS check should happen at all.
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: _addrinfo(addr))
    login_as(admin_user)
    resp = client.post(
        "/api/webhooks",
        json={
            "name": "dev-internal",
            "target_url": "https://internal.dev/hook",
            "event_types": ["firewatch.test"],
        },
    )
    assert resp.status_code == 201


def test_create_rejects_dns_failure_in_prod_with_clean_422(
    client, admin_user, login_as, monkeypatch
):
    login_as(admin_user)
    _enter_prod(monkeypatch)

    def boom(*args, **kwargs):
        raise socket.gaierror("name does not resolve")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    resp = client.post(
        "/api/webhooks",
        json={
            "name": "nxdomain",
            "target_url": "https://no-such-host.example.invalid/hook",
            "event_types": ["firewatch.test"],
        },
    )
    assert resp.status_code == 422
    assert "DNS resolution failed" in resp.json()["detail"]


def test_patch_rejects_internal_url_in_prod(
    client, admin_user, login_as, monkeypatch
):
    # Create in debug mode (any URL is fine), then flip to prod and try to PATCH
    # the URL to one that resolves to a private IP — must be rejected.
    login_as(admin_user)
    created = _create(client)

    _enter_prod(monkeypatch)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: _addrinfo("10.0.0.5"))
    resp = client.patch(
        f"/api/webhooks/{created['id']}",
        json={"target_url": "https://internal.example.com/hook"},
    )
    assert resp.status_code == 422
    assert "private/internal IP" in resp.json()["detail"]


def test_create_accepts_public_https_url_end_to_end(
    client, admin_user, login_as, monkeypatch
):
    login_as(admin_user)
    _enter_prod(monkeypatch)
    _public_dns(monkeypatch)
    resp = client.post(
        "/api/webhooks",
        json={
            "name": "public",
            "target_url": "https://example.com/hook",
            "event_types": ["firewatch.test"],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["target_url"] == "https://example.com/hook"
    assert body["secret"]

