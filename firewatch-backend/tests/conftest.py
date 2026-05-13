"""Shared pytest fixtures for the Firewatch backend test suite."""

from __future__ import annotations

import secrets
import time
from typing import Any, Callable, Generator

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import RSAKey
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import oidc as oidc_module
from app.core.config import settings
from app.core.dependencies import get_db
from app.core.security import hash_password
from app.models.database import Base
from app.models.user import User, UserRole
from main import app


# --- RSA keypair (session-scoped) -------------------------------------------------


@pytest.fixture(scope="session")
def rsa_key() -> RSAKey:
    """One RSA-2048 keypair shared across the whole test session."""
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return RSAKey.import_key(pem, parameters={"kid": "test-kid-1", "use": "sig", "alg": "RS256"})


@pytest.fixture(scope="session")
def jwks(rsa_key: RSAKey) -> dict[str, Any]:
    """Public-side JWKS dict for the test signing key."""
    return {"keys": [rsa_key.as_dict(private=False)]}


# --- Token factory ---------------------------------------------------------------


@pytest.fixture
def fake_id_token(rsa_key: RSAKey) -> Callable[..., str]:
    """Mint a signed id_token, with overridable claims."""

    def _make(**overrides: Any) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": "https://test-idp.example.com",
            "aud": "test-client-id",
            "sub": "test-sub-123",
            "email": "test@example.com",
            "name": "Test User",
            "nonce": "test-nonce",
            "exp": now + 3600,
            "iat": now,
        }
        claims.update(overrides)
        header = {"alg": "RS256", "kid": rsa_key.kid}
        return jwt.encode(header, claims, rsa_key)

    return _make


# --- OIDC settings ---------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_sso_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset OIDC + SCIM settings to declared defaults so a real .env can't leak in.

    Autouse + function-scoped so it runs before every test. Tests that need a
    configured OIDC opt back in via the `oidc_settings` fixture, which will
    override these resets (fixture resolution is LIFO within a test).
    """
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)
    monkeypatch.setattr(settings, "OIDC_PROVIDER_NAME", "SSO")
    monkeypatch.setattr(settings, "OIDC_DISCOVERY_URL", None)
    monkeypatch.setattr(settings, "OIDC_CLIENT_ID", None)
    monkeypatch.setattr(settings, "OIDC_CLIENT_SECRET", None)
    monkeypatch.setattr(settings, "OIDC_REDIRECT_URI", None)
    monkeypatch.setattr(settings, "OIDC_SCOPES", "openid email profile")
    monkeypatch.setattr(settings, "OIDC_DEFAULT_ROLE", "risk_owner")
    monkeypatch.setattr(settings, "OIDC_ROLE_CLAIM", "groups")
    monkeypatch.setattr(settings, "OIDC_ROLE_MAP", {})
    monkeypatch.setattr(settings, "SCIM_ENABLED", False)
    monkeypatch.setattr(settings, "SCIM_BEARER_TOKEN", None)


@pytest.fixture
def oidc_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch settings so OIDC is 'configured' for the test."""
    monkeypatch.setattr(settings, "OIDC_ENABLED", True)
    monkeypatch.setattr(settings, "OIDC_PROVIDER_NAME", "Test SSO")
    monkeypatch.setattr(
        settings, "OIDC_DISCOVERY_URL",
        "https://test-idp.example.com/.well-known/openid-configuration",
    )
    monkeypatch.setattr(settings, "OIDC_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "OIDC_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(
        settings, "OIDC_REDIRECT_URI",
        "http://localhost:3000/api/auth/sso/callback",
    )
    monkeypatch.setattr(settings, "OIDC_SCOPES", "openid email profile")
    monkeypatch.setattr(settings, "OIDC_DEFAULT_ROLE", "risk_owner")
    monkeypatch.setattr(settings, "OIDC_ROLE_CLAIM", "groups")
    monkeypatch.setattr(settings, "OIDC_ROLE_MAP", {})
    monkeypatch.setattr(settings, "FRONTEND_URL", "http://localhost:3000")
    monkeypatch.setattr(settings, "DEBUG", True)


@pytest.fixture(autouse=True)
def _clear_oidc_caches() -> None:
    """Wipe the OIDC discovery + JWKS caches before every test."""
    oidc_module._DISCOVERY_CACHE.clear()
    oidc_module._JWKS_CACHE.clear()


@pytest.fixture(autouse=True)
def _disable_rate_limiter() -> Generator[None, None, None]:
    """Turn off the SlowAPI limiter so multi-call tests don't hit 429."""
    app.state.limiter.enabled = False
    yield
    app.state.limiter.enabled = True


@pytest.fixture
def mock_discovery() -> dict[str, str]:
    """Discovery doc matching the test issuer."""
    return {
        "issuer": "https://test-idp.example.com",
        "authorization_endpoint": "https://test-idp.example.com/authorize",
        "token_endpoint": "https://test-idp.example.com/token",
        "jwks_uri": "https://test-idp.example.com/jwks",
        "end_session_endpoint": "https://test-idp.example.com/logout",
    }


# --- Database --------------------------------------------------------------------


@pytest.fixture
def db():
    """In-memory SQLite shared across threads via StaticPool."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db):
    """TestClient with the get_db dependency overridden to the in-memory session."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


# --- User fixtures ---------------------------------------------------------------


@pytest.fixture
def existing_local_user(db) -> User:
    user = User(
        email="local@example.com",
        full_name="Local User",
        hashed_password=hash_password("SecretPass123!"),
        role=UserRole.risk_owner,
        auth_provider="local",
        external_id=None,
        is_active=True,
        must_change_password=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def disabled_sso_user(db) -> User:
    user = User(
        email="disabled@example.com",
        full_name="Disabled SSO",
        hashed_password=None,
        role=UserRole.risk_owner,
        auth_provider="oidc",
        external_id="disabled-sub",
        is_active=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# --- Role-based user factories + login helper -----------------------------------


def _make_user(db, *, email: str, role: UserRole, password: str = "SecretPass123!") -> User:
    user = User(
        email=email,
        full_name=f"{role.value} user",
        hashed_password=hash_password(password),
        role=role,
        auth_provider="local",
        is_active=True,
        must_change_password=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_user(db) -> User:
    return _make_user(db, email="admin@example.com", role=UserRole.admin)


@pytest.fixture
def analyst_user(db) -> User:
    return _make_user(db, email="analyst@example.com", role=UserRole.security_analyst)


@pytest.fixture
def owner_user(db) -> User:
    return _make_user(db, email="owner@example.com", role=UserRole.risk_owner)


@pytest.fixture
def owner_user_b(db) -> User:
    return _make_user(db, email="owner-b@example.com", role=UserRole.risk_owner)


@pytest.fixture
def viewer_user(db) -> User:
    return _make_user(db, email="viewer@example.com", role=UserRole.executive_viewer)


@pytest.fixture
def login_as(client):
    """Return a callable that logs the given user in via /api/auth/login."""

    def _login(user: User, password: str = "SecretPass123!") -> None:
        resp = client.post(
            "/api/auth/login", json={"email": user.email, "password": password}
        )
        assert resp.status_code == 200, resp.text

    return _login
