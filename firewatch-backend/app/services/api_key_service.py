"""API key generation, lookup, and lifecycle helpers."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.api_key import ApiKey


KEY_PREFIX = "fwk_"
# Number of url-safe characters (after the fwk_ prefix) we persist as an
# indexed lookup key. 8 chars of 64-symbol alphabet = 48 bits ≈ low collision
# risk while keeping the column tiny.
PREFIX_LEN = 8


def generate_key() -> tuple[str, str, str]:
    """Return (plaintext, prefix, hashed_key) for a freshly minted key."""
    random_part = secrets.token_urlsafe(32)
    plaintext = f"{KEY_PREFIX}{random_part}"
    prefix = random_part[:PREFIX_LEN]
    hashed_key = hash_key(plaintext)
    return plaintext, prefix, hashed_key


def hash_key(plaintext: str) -> str:
    """sha256 hex digest of the entire plaintext key (including the fwk_ prefix)."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def lookup_by_plaintext(db: Session, plaintext: str) -> ApiKey | None:
    """Resolve a plaintext key to its ApiKey row, or None if invalid/expired/revoked."""
    if not plaintext.startswith(KEY_PREFIX):
        return None
    random_part = plaintext[len(KEY_PREFIX):]
    if len(random_part) < PREFIX_LEN:
        return None
    prefix = random_part[:PREFIX_LEN]
    now = datetime.now(timezone.utc)

    candidates = (
        db.query(ApiKey)
        .filter(
            ApiKey.prefix == prefix,
            ApiKey.revoked_at.is_(None),
            or_(ApiKey.expires_at.is_(None), ApiKey.expires_at > now),
        )
        .all()
    )

    digest = hash_key(plaintext)
    for candidate in candidates:
        # Timing-safe comparison so partial-match attacks can't infer characters.
        if secrets.compare_digest(candidate.hashed_key, digest):
            return candidate
    return None


def create(
    db: Session,
    *,
    user_id: int,
    name: str,
    expires_at: datetime | None,
) -> tuple[ApiKey, str]:
    """Generate a new key, persist it, and return (row, plaintext)."""
    plaintext, prefix, hashed_key = generate_key()
    row = ApiKey(
        user_id=user_id,
        name=name,
        prefix=prefix,
        hashed_key=hashed_key,
        expires_at=expires_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, plaintext


def list_for_user(db: Session, user_id: int) -> list[ApiKey]:
    """Return the user's API keys ordered newest-first."""
    return (
        db.query(ApiKey)
        .filter(ApiKey.user_id == user_id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )


def list_all(db: Session) -> list[ApiKey]:
    """All API keys across all users, ordered created_at desc, with owner eager-loaded."""
    return (
        db.query(ApiKey)
        .options(joinedload(ApiKey.owner))
        .order_by(ApiKey.created_at.desc())
        .all()
    )


def revoke(db: Session, key: ApiKey) -> None:
    """Mark a key revoked. Caller commits."""
    key.revoked_at = datetime.now(timezone.utc)
