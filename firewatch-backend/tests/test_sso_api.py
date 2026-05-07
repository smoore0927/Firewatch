"""Integration tests for /api/auth/sso routes."""

from __future__ import annotations

import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from joserfc import jwt

from app.core.config import settings
from app.core.oidc import (
    OIDC_FLOW_COOKIE,
    OIDC_FLOW_COOKIE_PATH,
    sign_flow_cookie,
)


# --- /config -------------------------------------------------------------------


def test_sso_config_returns_disabled_by_default(client):
    resp = client.get("/api/auth/sso/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"enabled": False, "provider_name": None}


def test_sso_config_returns_enabled_when_configured(client, oidc_settings):
    resp = client.get("/api/auth/sso/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["provider_name"] == "Test SSO"


# --- /login --------------------------------------------------------------------


def test_sso_login_when_not_configured_redirects_to_error(client):
    resp = client.get("/api/auth/sso/login", follow_redirects=False)
    assert resp.status_code == 302
    assert "sso_error=not_configured" in resp.headers["location"]


def test_sso_login_redirects_to_idp_with_cookie(
    client, oidc_settings, mock_discovery
):
    with respx.mock:
        respx.get(
            "https://test-idp.example.com/.well-known/openid-configuration"
        ).mock(return_value=httpx.Response(200, json=mock_discovery))
        resp = client.get("/api/auth/sso/login", follow_redirects=False)

    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith("https://test-idp.example.com/authorize?")
    qs = parse_qs(urlparse(location).query)
    assert qs["client_id"] == ["test-client-id"]
    assert qs["response_type"] == ["code"]
    assert qs["code_challenge_method"] == ["S256"]
    assert "code_challenge" in qs
    assert "state" in qs
    assert "nonce" in qs
    # Flow cookie set on the response.
    assert OIDC_FLOW_COOKIE in resp.cookies


def test_sso_login_when_discovery_fails_redirects_to_error(
    client, oidc_settings
):
    with respx.mock:
        respx.get(
            "https://test-idp.example.com/.well-known/openid-configuration"
        ).mock(return_value=httpx.Response(500))
        resp = client.get("/api/auth/sso/login", follow_redirects=False)
    assert resp.status_code == 302
    assert "sso_error=discovery_failed" in resp.headers["location"]


# --- /callback errors ----------------------------------------------------------


def test_sso_callback_no_cookie_redirects_to_invalid_state(client, oidc_settings):
    resp = client.get(
        "/api/auth/sso/callback?code=abc&state=xyz", follow_redirects=False
    )
    assert resp.status_code == 302
    assert "sso_error=invalid_state" in resp.headers["location"]


def test_sso_callback_state_mismatch_redirects(client, oidc_settings):
    cookie_payload = sign_flow_cookie(
        {"state": "real-state", "nonce": "n", "code_verifier": "v"}
    )
    client.cookies.set(
        OIDC_FLOW_COOKIE, cookie_payload, path=OIDC_FLOW_COOKIE_PATH
    )
    resp = client.get(
        "/api/auth/sso/callback?code=abc&state=wrong-state",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "sso_error=state_mismatch" in resp.headers["location"]


def test_sso_callback_provider_error(client, oidc_settings):
    resp = client.get(
        "/api/auth/sso/callback?error=access_denied", follow_redirects=False
    )
    assert resp.status_code == 302
    assert "sso_error=provider_error" in resp.headers["location"]


# --- /callback happy path ------------------------------------------------------


@pytest.mark.asyncio
async def test_sso_callback_happy_path(
    client, oidc_settings, mock_discovery, rsa_key, jwks
):
    state = "test-state-value"
    nonce = "test-nonce-value"
    cookie_payload = sign_flow_cookie(
        {"state": state, "nonce": nonce, "code_verifier": "the-verifier"}
    )
    client.cookies.set(
        OIDC_FLOW_COOKIE, cookie_payload, path=OIDC_FLOW_COOKIE_PATH
    )

    now = int(time.time())
    id_token = jwt.encode(
        {"alg": "RS256", "kid": rsa_key.kid},
        {
            "iss": "https://test-idp.example.com",
            "aud": "test-client-id",
            "sub": "happy-sub",
            "email": "happy@example.com",
            "email_verified": True,
            "name": "Happy User",
            "nonce": nonce,
            "exp": now + 3600,
            "iat": now,
        },
        rsa_key,
    )

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

        resp = client.get(
            f"/api/auth/sso/callback?code=auth-code&state={state}",
            follow_redirects=False,
        )

    assert resp.status_code == 302
    assert resp.headers["location"] == f"{settings.FRONTEND_URL}/dashboard"
    # Auth cookies issued.
    assert "access_token" in resp.cookies
    assert "refresh_token" in resp.cookies
    # The flow cookie was deleted — Set-Cookie: oidc_flow=""; Max-Age=0
    set_cookie_headers = resp.headers.get_list("set-cookie") if hasattr(
        resp.headers, "get_list"
    ) else [v for k, v in resp.headers.multi_items() if k.lower() == "set-cookie"]
    assert any(
        OIDC_FLOW_COOKIE in h and ("Max-Age=0" in h or 'oidc_flow=""' in h)
        for h in set_cookie_headers
    )
