"""Unit tests for app.core.oidc helpers and id_token verification."""

from __future__ import annotations

import base64
import hashlib
import time
from typing import Any

import httpx
import pytest
import respx
from joserfc import jwt
from joserfc.jwk import RSAKey

from app.core import oidc as oidc_module
from app.core.oidc import (
    _b64url,
    generate_pkce_pair,
    read_flow_cookie,
    sign_flow_cookie,
    verify_id_token,
)


# --- Pure helpers ---------------------------------------------------------------


def test_b64url_strips_padding():
    # Input chosen so that standard base64 would produce "==" padding.
    raw = b"\x01\x02"
    out = _b64url(raw)
    assert "=" not in out
    # Round-trip after re-padding.
    padded = out + "=" * (-len(out) % 4)
    assert base64.urlsafe_b64decode(padded.encode("ascii")) == raw


def test_pkce_pair_challenge_matches_verifier():
    verifier, challenge = generate_pkce_pair()
    expected = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    assert challenge == expected
    assert 43 <= len(verifier) <= 128


# --- Flow cookie ----------------------------------------------------------------


def test_flow_cookie_round_trip():
    payload = {"state": "abc", "nonce": "def", "code_verifier": "ghi"}
    cookie = sign_flow_cookie(payload)
    decoded = read_flow_cookie(cookie)
    assert decoded == payload


def test_flow_cookie_rejects_tampered():
    payload = {"state": "abc", "nonce": "def", "code_verifier": "ghi"}
    cookie = sign_flow_cookie(payload)
    tampered = cookie[:-2] + ("AA" if cookie[-2:] != "AA" else "BB")
    assert read_flow_cookie(tampered) is None


# --- verify_id_token: claim validation ------------------------------------------


def _mock_jwks(jwks: dict[str, Any]):
    """Helper to mock the JWKS endpoint."""
    return respx.get("https://test-idp.example.com/jwks").mock(
        return_value=httpx.Response(200, json=jwks)
    )


@pytest.mark.asyncio
async def test_verify_id_token_happy_path(oidc_settings, fake_id_token, jwks):
    token = fake_id_token()
    with respx.mock:
        _mock_jwks(jwks)
        claims = await verify_id_token(
            token,
            issuer="https://test-idp.example.com",
            jwks_uri="https://test-idp.example.com/jwks",
            expected_nonce="test-nonce",
        )
    assert claims["sub"] == "test-sub-123"
    assert claims["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_verify_id_token_rejects_wrong_issuer(oidc_settings, fake_id_token, jwks):
    token = fake_id_token(iss="https://evil.example.com")
    with respx.mock:
        _mock_jwks(jwks)
        with pytest.raises(ValueError, match="issuer mismatch"):
            await verify_id_token(
                token,
                issuer="https://test-idp.example.com",
                jwks_uri="https://test-idp.example.com/jwks",
                expected_nonce="test-nonce",
            )


@pytest.mark.asyncio
async def test_verify_id_token_rejects_wrong_audience(oidc_settings, fake_id_token, jwks):
    token = fake_id_token(aud="some-other-client")
    with respx.mock:
        _mock_jwks(jwks)
        with pytest.raises(ValueError, match="audience mismatch"):
            await verify_id_token(
                token,
                issuer="https://test-idp.example.com",
                jwks_uri="https://test-idp.example.com/jwks",
                expected_nonce="test-nonce",
            )


@pytest.mark.asyncio
async def test_verify_id_token_rejects_expired(oidc_settings, fake_id_token, jwks):
    now = int(time.time())
    token = fake_id_token(exp=now - 60, iat=now - 3600)
    with respx.mock:
        _mock_jwks(jwks)
        with pytest.raises(ValueError, match="token expired"):
            await verify_id_token(
                token,
                issuer="https://test-idp.example.com",
                jwks_uri="https://test-idp.example.com/jwks",
                expected_nonce="test-nonce",
            )


@pytest.mark.asyncio
async def test_verify_id_token_rejects_wrong_nonce(oidc_settings, fake_id_token, jwks):
    token = fake_id_token(nonce="some-other-nonce")
    with respx.mock:
        _mock_jwks(jwks)
        with pytest.raises(ValueError, match="nonce mismatch"):
            await verify_id_token(
                token,
                issuer="https://test-idp.example.com",
                jwks_uri="https://test-idp.example.com/jwks",
                expected_nonce="test-nonce",
            )


# --- at_hash validation ---------------------------------------------------------


def _compute_at_hash(access_token: str) -> str:
    digest = hashlib.sha256(access_token.encode()).digest()
    return _b64url(digest[: len(digest) // 2])


@pytest.mark.asyncio
async def test_at_hash_validation_passes_correct_hash(oidc_settings, fake_id_token, jwks):
    access_token = "fake-access-token-xyz"
    token = fake_id_token(at_hash=_compute_at_hash(access_token))
    with respx.mock:
        _mock_jwks(jwks)
        claims = await verify_id_token(
            token,
            issuer="https://test-idp.example.com",
            jwks_uri="https://test-idp.example.com/jwks",
            expected_nonce="test-nonce",
            access_token=access_token,
        )
    assert claims["at_hash"] == _compute_at_hash(access_token)


@pytest.mark.asyncio
async def test_at_hash_mismatch_raises(oidc_settings, fake_id_token, jwks):
    """Gap 3 regression — at_hash present but doesn't match access_token."""
    access_token = "real-access-token"
    bad_hash = _compute_at_hash("a-different-token")
    token = fake_id_token(at_hash=bad_hash)
    with respx.mock:
        _mock_jwks(jwks)
        with pytest.raises(ValueError, match="at_hash mismatch"):
            await verify_id_token(
                token,
                issuer="https://test-idp.example.com",
                jwks_uri="https://test-idp.example.com/jwks",
                expected_nonce="test-nonce",
                access_token=access_token,
            )


@pytest.mark.asyncio
async def test_at_hash_skipped_when_no_access_token(oidc_settings, fake_id_token, jwks):
    """Token includes at_hash but caller passes access_token=None — no validation, no raise."""
    token = fake_id_token(at_hash="any-value-because-we-skip")
    with respx.mock:
        _mock_jwks(jwks)
        claims = await verify_id_token(
            token,
            issuer="https://test-idp.example.com",
            jwks_uri="https://test-idp.example.com/jwks",
            expected_nonce="test-nonce",
            access_token=None,
        )
    assert claims["sub"] == "test-sub-123"


# --- JWKS rotation fallback (Gap 2 regression) ---------------------------------


@pytest.mark.asyncio
async def test_jwks_rotation_fallback(oidc_settings, fake_id_token):
    """If decode fails against cached JWKS, the cache is dropped and re-fetched once."""
    # Stale key already in the cache — different from the key we'll sign with.
    stale_key = RSAKey.generate_key(2048, parameters={"kid": "stale-kid", "use": "sig", "alg": "RS256"})
    stale_jwks = {"keys": [stale_key.as_dict(private=False)]}
    oidc_module._JWKS_CACHE["https://test-idp.example.com/jwks"] = (
        time.time() + 3600,
        __import__("joserfc").jwk.KeySet.import_key_set(stale_jwks),
    )

    # Fresh keypair the IdP "rotated" to.
    new_key = RSAKey.generate_key(2048, parameters={"kid": "new-kid", "use": "sig", "alg": "RS256"})
    new_jwks = {"keys": [new_key.as_dict(private=False)]}

    now = int(time.time())
    claims = {
        "iss": "https://test-idp.example.com",
        "aud": "test-client-id",
        "sub": "test-sub-123",
        "email": "test@example.com",
        "nonce": "test-nonce",
        "exp": now + 3600,
        "iat": now,
    }
    header = {"alg": "RS256", "kid": new_key.kid}
    token = jwt.encode(header, claims, new_key)

    with respx.mock:
        route = respx.get("https://test-idp.example.com/jwks").mock(
            return_value=httpx.Response(200, json=new_jwks)
        )
        result = await verify_id_token(
            token,
            issuer="https://test-idp.example.com",
            jwks_uri="https://test-idp.example.com/jwks",
            expected_nonce="test-nonce",
        )
        # The first decode failed against the stale cache, so the JWKS endpoint was hit exactly once.
        assert route.call_count == 1
    assert result["sub"] == "test-sub-123"
