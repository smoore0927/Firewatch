"""End-to-end audit instrumentation tests for the OIDC SSO callback flow.

Closes the gap noted in tests/test_audit_instrumentation.py: each `record_event`
call site in app/api/sso.py is exercised by mocking the IdP discovery, JWKS, and
token endpoints (mirroring the canonical happy-path mocking pattern used in
tests/test_sso_api.py::test_sso_callback_happy_path).
"""

from __future__ import annotations

import json
import time

import httpx
import pytest
import respx
from joserfc import jwt

from app.core.oidc import (
    OIDC_FLOW_COOKIE,
    OIDC_FLOW_COOKIE_PATH,
    sign_flow_cookie,
)
from app.models.audit_log import AuditLog


# --- helpers -----------------------------------------------------------------


_STATE = "test-state-value"
_NONCE = "test-nonce-value"


def _latest(db, *, action: str) -> AuditLog | None:
    return (
        db.query(AuditLog)
        .filter(AuditLog.action == action)
        .order_by(AuditLog.id.desc())
        .first()
    )


def _set_flow_cookie(client) -> None:
    payload = sign_flow_cookie(
        {"state": _STATE, "nonce": _NONCE, "code_verifier": "the-verifier"}
    )
    client.cookies.set(OIDC_FLOW_COOKIE, payload, path=OIDC_FLOW_COOKIE_PATH)


def _make_id_token(rsa_key, **claim_overrides):
    """
    Build a signed id_token. Unlike the conftest `fake_id_token` fixture, this
    helper lets the caller *omit* claims (e.g. `sub` or `email`) by passing
    them as `None` — those keys are removed entirely from the payload.
    """
    now = int(time.time())
    claims: dict = {
        "iss": "https://test-idp.example.com",
        "aud": "test-client-id",
        "sub": "audit-sub",
        "email": "audit@example.com",
        "email_verified": True,
        "name": "Audit User",
        "nonce": _NONCE,
        "exp": now + 3600,
        "iat": now,
    }
    for key, value in claim_overrides.items():
        if value is None:
            claims.pop(key, None)
        else:
            claims[key] = value
    header = {"alg": "RS256", "kid": rsa_key.kid}
    return jwt.encode(header, claims, rsa_key)


def _run_callback(client, mock_discovery, jwks, id_token: str):
    """Mock the IdP endpoints and drive the callback once. Returns the response."""
    with respx.mock:
        respx.get(
            "https://test-idp.example.com/.well-known/openid-configuration"
        ).mock(return_value=httpx.Response(200, json=mock_discovery))
        respx.get("https://test-idp.example.com/jwks").mock(
            return_value=httpx.Response(200, json=jwks)
        )
        respx.post("https://test-idp.example.com/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "fake-access",
                    "id_token": id_token,
                    "token_type": "Bearer",
                },
            )
        )
        return client.get(
            f"/api/auth/sso/callback?code=auth-code&state={_STATE}",
            follow_redirects=False,
        )


# --- success hook -------------------------------------------------------------


@pytest.mark.asyncio
async def test_sso_callback_success_records_audit_row(
    client, db, oidc_settings, mock_discovery, rsa_key, jwks
):
    _set_flow_cookie(client)
    id_token = _make_id_token(
        rsa_key, sub="happy-sub", email="happy@example.com", name="Happy User"
    )

    resp = _run_callback(client, mock_discovery, jwks, id_token)

    assert resp.status_code == 302
    assert resp.headers["location"].endswith("/dashboard")

    row = _latest(db, action="auth.sso.login.success")
    assert row is not None
    assert row.resource_type == "auth"
    assert row.user_email == "happy@example.com"
    assert row.user_id is not None  # JIT-provisioned user
    assert row.ip_address  # TestClient populates request.client.host
    assert json.loads(row.details) == {"method": "oidc"}


# --- failure hooks ------------------------------------------------------------


@pytest.mark.asyncio
async def test_sso_callback_missing_sub_records_audit_row(
    client, db, oidc_settings, mock_discovery, rsa_key, jwks
):
    """`joserfc` does not require `sub`, and `verify_id_token` does not check it,
    so omitting `sub` reaches `provision_sso_user` and triggers SSOMissingSubError.
    The hook records the email claim that was still in the token."""
    _set_flow_cookie(client)
    id_token = _make_id_token(rsa_key, sub=None, email="orphan@example.com")

    resp = _run_callback(client, mock_discovery, jwks, id_token)

    assert resp.status_code == 302
    assert "sso_error=invalid_id_token" in resp.headers["location"]

    row = _latest(db, action="auth.sso.login.failed")
    assert row is not None
    assert row.resource_type == "auth"
    assert row.user_id is None
    # Per app/api/sso.py: user_email falls back to claims.get("email").
    assert row.user_email == "orphan@example.com"
    assert row.ip_address
    assert json.loads(row.details) == {"reason": "invalid_id_token"}


@pytest.mark.asyncio
async def test_sso_callback_no_email_records_audit_row(
    client, db, oidc_settings, mock_discovery, rsa_key, jwks
):
    _set_flow_cookie(client)
    id_token = _make_id_token(rsa_key, email=None)

    resp = _run_callback(client, mock_discovery, jwks, id_token)

    assert resp.status_code == 302
    assert "sso_error=no_email" in resp.headers["location"]

    row = _latest(db, action="auth.sso.login.failed")
    assert row is not None
    assert row.resource_type == "auth"
    assert row.user_id is None
    # No email claim was present, so the fallback is None.
    assert row.user_email is None
    assert row.ip_address
    assert json.loads(row.details) == {"reason": "no_email"}


@pytest.mark.asyncio
async def test_sso_callback_email_not_verified_records_audit_row(
    client, db, oidc_settings, mock_discovery, rsa_key, jwks
):
    _set_flow_cookie(client)
    id_token = _make_id_token(
        rsa_key, email="unverified@example.com", email_verified=False
    )

    resp = _run_callback(client, mock_discovery, jwks, id_token)

    assert resp.status_code == 302
    assert "sso_error=email_not_verified" in resp.headers["location"]

    row = _latest(db, action="auth.sso.login.failed")
    assert row is not None
    assert row.resource_type == "auth"
    assert row.user_id is None
    assert row.user_email == "unverified@example.com"
    assert row.ip_address
    assert json.loads(row.details) == {"reason": "email_not_verified"}


@pytest.mark.asyncio
async def test_sso_callback_account_disabled_records_audit_row(
    client, db, oidc_settings, mock_discovery, rsa_key, jwks, disabled_sso_user
):
    _set_flow_cookie(client)
    id_token = _make_id_token(
        rsa_key,
        sub=disabled_sso_user.external_id,
        email=disabled_sso_user.email,
    )

    resp = _run_callback(client, mock_discovery, jwks, id_token)

    assert resp.status_code == 302
    assert "sso_error=account_disabled" in resp.headers["location"]

    row = _latest(db, action="auth.sso.login.failed")
    assert row is not None
    assert row.resource_type == "auth"
    assert row.user_id is None  # the failure hook does not pass `user`
    assert row.user_email == disabled_sso_user.email
    assert row.ip_address
    assert json.loads(row.details) == {"reason": "account_disabled"}
