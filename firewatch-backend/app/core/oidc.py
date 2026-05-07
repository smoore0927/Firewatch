"""
OIDC client + ID token verification helpers.

We deliberately avoid Starlette's SessionMiddleware — adding a global session would
introduce server-side state for every request. Instead:

  - state, nonce, PKCE code_verifier are generated per-request
  - all three are signed and stored in a short-lived HTTP-only cookie scoped to /api/auth/sso/callback
  - the cookie is verified, consumed, and deleted on the callback hop
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from typing import Any

import httpx
from fastapi import HTTPException, status
from itsdangerous import BadSignature, URLSafeTimedSerializer
from joserfc import jwt
from joserfc.jwk import KeySet

from app.core.config import settings


OIDC_FLOW_COOKIE = "oidc_flow"
OIDC_FLOW_COOKIE_PATH = "/api/auth/sso/callback"
OIDC_FLOW_TTL_SECONDS = 600  # 10 minutes

_DISCOVERY_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_JWKS_CACHE: dict[str, tuple[float, Any]] = {}
_DISCOVERY_TTL = 3600  # 1h
_JWKS_TTL = 3600  # 1h


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.SECRET_KEY, salt="oidc-state")


def require_oidc_configured() -> None:
    """Raise 503 if SSO isn't configured. Used by routes that must have a working IdP."""
    if not settings.oidc_is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SSO is not configured",
        )


async def get_discovery_document() -> dict[str, Any]:
    """Fetch & cache the IdP's discovery doc (.well-known/openid-configuration)."""
    require_oidc_configured()
    url = settings.OIDC_DISCOVERY_URL  # type: ignore[assignment]
    cached = _DISCOVERY_CACHE.get(url)  # type: ignore[arg-type]
    now = time.time()
    if cached and cached[0] > now:
        return cached[1]
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)  # type: ignore[arg-type]
        resp.raise_for_status()
        doc = resp.json()
    _DISCOVERY_CACHE[url] = (now + _DISCOVERY_TTL, doc)  # type: ignore[index]
    return doc


async def get_jwks(jwks_uri: str) -> KeySet:
    """Fetch & cache the IdP's JWKS for signature verification."""
    cached = _JWKS_CACHE.get(jwks_uri)
    now = time.time()
    if cached and cached[0] > now:
        return cached[1]
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(jwks_uri)
        resp.raise_for_status()
        keys = KeySet.import_key_set(resp.json())
    _JWKS_CACHE[jwks_uri] = (now + _JWKS_TTL, keys)
    return keys


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for PKCE S256."""
    verifier = _b64url(secrets.token_bytes(64))  # 86 chars, well within 43–128
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def generate_flow_secrets() -> dict[str, str]:
    """Fresh state, nonce, and PKCE verifier/challenge for one auth attempt."""
    verifier, challenge = generate_pkce_pair()
    return {
        "state": secrets.token_urlsafe(32),
        "nonce": secrets.token_urlsafe(32),
        "code_verifier": verifier,
        "code_challenge": challenge,
    }


def sign_flow_cookie(payload: dict[str, str]) -> str:
    return _serializer().dumps(payload)


def read_flow_cookie(raw: str) -> dict[str, str] | None:
    """Returns the decoded payload, or None if missing/expired/tampered."""
    try:
        return _serializer().loads(raw, max_age=OIDC_FLOW_TTL_SECONDS)
    except BadSignature:
        return None


def build_authorization_url(authorization_endpoint: str, secrets_bundle: dict[str, str]) -> str:
    """Hand-build the auth URL — we already have all the pieces, no extra OAuth lib needed."""
    from urllib.parse import urlencode

    params = {
        "response_type": "code",
        "client_id": settings.OIDC_CLIENT_ID,
        "redirect_uri": settings.OIDC_REDIRECT_URI,
        "scope": settings.OIDC_SCOPES,
        "state": secrets_bundle["state"],
        "nonce": secrets_bundle["nonce"],
        "code_challenge": secrets_bundle["code_challenge"],
        "code_challenge_method": "S256",
    }
    sep = "&" if "?" in authorization_endpoint else "?"
    return f"{authorization_endpoint}{sep}{urlencode(params)}"


async def exchange_code_for_tokens(
    token_endpoint: str, code: str, code_verifier: str
) -> dict[str, Any]:
    """POST to the IdP's token endpoint with PKCE verifier."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.OIDC_REDIRECT_URI,
        "client_id": settings.OIDC_CLIENT_ID,
        "client_secret": settings.OIDC_CLIENT_SECRET,
        "code_verifier": code_verifier,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            token_endpoint,
            data=data,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()


async def verify_id_token(
    id_token: str, issuer: str, jwks_uri: str, expected_nonce: str
) -> dict[str, Any]:
    """
    Validate the id_token's signature and claims (iss, aud, exp, nonce).
    Returns the claims dict on success, raises ValueError otherwise.
    """
    keys = await get_jwks(jwks_uri)
    decoded = jwt.decode(id_token, keys)
    claims = dict(decoded.claims)

    if claims.get("iss") != issuer:
        raise ValueError("issuer mismatch")

    aud = claims.get("aud")
    aud_list = aud if isinstance(aud, list) else [aud]
    if settings.OIDC_CLIENT_ID not in aud_list:
        raise ValueError("audience mismatch")

    exp = claims.get("exp")
    if not exp or int(exp) < int(time.time()):
        raise ValueError("token expired")

    if claims.get("nonce") != expected_nonce:
        raise ValueError("nonce mismatch")

    return claims
