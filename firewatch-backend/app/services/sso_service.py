"""SSO user provisioning — JIT account creation and account linking."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)


class SSOAccountDisabledError(Exception):
    """Matched user exists but is_active=False."""


class SSONoEmailError(Exception):
    """IdP did not return an email claim."""


class SSOMissingSubError(Exception):
    """IdP did not return a sub claim."""


_ROLE_PRIVILEGE = {
    UserRole.admin: 4,
    UserRole.security_analyst: 3,
    UserRole.risk_owner: 2,
    UserRole.executive_viewer: 1,
}


def _resolve_role_from_claims(claims: dict[str, Any]) -> UserRole:
    """Resolve a UserRole from id_token claims, or fall back to OIDC_DEFAULT_ROLE."""
    default = UserRole(settings.OIDC_DEFAULT_ROLE)

    # Entra "group overage" — too many groups, IdP omits them and references via Graph.
    claim_names = claims.get("_claim_names")
    if isinstance(claim_names, dict) and "groups" in claim_names:
        logger.warning(
            "OIDC group overage detected for sub=%s — role mapping will fall back to default",
            claims.get("sub"),
        )

    if not settings.OIDC_ROLE_MAP:
        return default

    raw = claims.get(settings.OIDC_ROLE_CLAIM)
    if raw is None:
        return default

    values = raw if isinstance(raw, list) else [raw]
    matched = [
        settings.OIDC_ROLE_MAP[v] for v in values if v in settings.OIDC_ROLE_MAP
    ]
    if not matched:
        return default
    return max(matched, key=_ROLE_PRIVILEGE.__getitem__)


def provision_sso_user(db: Session, claims: dict[str, Any]) -> User:
    """
    Look up or create a user from OIDC claims.

    Order of resolution:
      1. external_id == sub  → existing SSO-linked account
      2. email (case-insensitive) → link by email and stamp external_id
      3. otherwise → JIT-create with auth_provider='oidc'

    The user's role is refreshed from the IdP claims on every login — this
    overwrites any role manually set in the UI.
    """
    sub = claims.get("sub")
    email = claims.get("email")
    full_name = claims.get("name")

    if not sub:
        raise SSOMissingSubError()
    if not email:
        raise SSONoEmailError()

    role = _resolve_role_from_claims(claims)

    user = db.query(User).filter(User.external_id == sub).first()
    if user:
        if not user.is_active:
            raise SSOAccountDisabledError()
        if user.role != role:
            user.role = role
            db.commit()
            db.refresh(user)
        return user

    user = (
        db.query(User)
        .filter(func.lower(User.email) == email.lower())
        .first()
    )
    if user:
        if not user.is_active:
            raise SSOAccountDisabledError()
        # Link the IdP identity. Don't touch hashed_password or auth_provider so
        # the user can still log in with whichever method they had before.
        changed = False
        if not user.external_id:
            user.external_id = sub
            changed = True
        if user.role != role:
            user.role = role
            changed = True
        if changed:
            db.commit()
            db.refresh(user)
        return user

    user = User(
        email=email,
        full_name=full_name,
        role=role,
        auth_provider="oidc",
        external_id=sub,
        hashed_password=None,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
