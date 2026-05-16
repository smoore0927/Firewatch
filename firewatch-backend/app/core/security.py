"""
Password hashing and JWT token creation/verification.

Why bcrypt?
  passlib's bcrypt is the industry standard for password storage. It's
  intentionally slow (work factor), salted automatically, and immune to
  rainbow table attacks. Never store plaintext or MD5/SHA passwords.

Why HTTP-only cookies for tokens (not localStorage)?
  JavaScript running in the browser (including injected XSS scripts) cannot
  read HTTP-only cookies. Tokens in localStorage are readable by any script
  on the page. HTTP-only cookies are the safer default for web apps.

Why two tokens (access + refresh)?
  Access tokens are short-lived (15 min). If one is stolen, the attacker's
  window is small. Refresh tokens let the frontend silently get new access
  tokens without re-login, and are scoped to a single endpoint path so they
  aren't sent on every request.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from fastapi import Response

from app.core.config import settings

# bcrypt has a hard limit of 72 bytes per password. Passwords longer than that
# are silently truncated, meaning "password123...73chars" == "password123...72chars".
# We enforce a 72-byte max in the schema (UserCreate.password) to make this explicit.
_BCRYPT_MAX_BYTES = 72


def hash_password(plain_password: str) -> str:
    """Return a bcrypt hash of the password. Store this, never the plain text."""
    password_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if plain_password matches the stored hash."""
    password_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))


def _create_token(
    subject: Any, token_type: str, expires_delta: timedelta, session_version: int
) -> str:
    """Internal: encode a JWT with a subject, type claim, sv claim, and expiry."""
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": str(subject),  # subject — usually the user's numeric ID
        "type": token_type,   # "access" or "refresh" — validated on decode
        "sv": session_version,  # session version — bumped on logout/password change
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(user_id: int, session_version: int) -> str:
    return _create_token(
        subject=user_id,
        token_type="access",
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        session_version=session_version,
    )


def create_refresh_token(user_id: int, session_version: int) -> str:
    return _create_token(
        subject=user_id,
        token_type="refresh",
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        session_version=session_version,
    )


def decode_token(token: str) -> dict:
    """
    Decode and verify a JWT. Raises jwt.PyJWTError on any failure
    (expired, tampered, wrong signature). Callers must catch JWT errors.
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def set_auth_cookies(response: Response, user_id: int, session_version: int) -> None:
    """Write both auth cookies. Shared by password login and OIDC callback."""
    response.set_cookie(
        key="access_token",
        value=create_access_token(user_id, session_version),
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=create_refresh_token(user_id, session_version),
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/auth/refresh",
    )
