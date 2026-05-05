"""SSO user provisioning — JIT account creation and account linking."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User, UserRole


class SSOAccountDisabledError(Exception):
    """Matched user exists but is_active=False."""


class SSONoEmailError(Exception):
    """IdP did not return an email claim."""


def _default_role() -> UserRole:
    """Resolve OIDC_DEFAULT_ROLE to a UserRole; raises ValueError if misconfigured."""
    return UserRole(settings.OIDC_DEFAULT_ROLE)


def provision_sso_user(
    db: Session, *, sub: str, email: str | None, full_name: str | None
) -> User:
    """
    Look up or create a user from OIDC claims.

    Order of resolution:
      1. external_id == sub  → existing SSO-linked account
      2. email (case-insensitive) → link by email and stamp external_id
      3. otherwise → JIT-create with auth_provider='oidc'
    """
    if not email:
        raise SSONoEmailError()

    user = db.query(User).filter(User.external_id == sub).first()
    if user:
        if not user.is_active:
            raise SSOAccountDisabledError()
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
        if not user.external_id:
            user.external_id = sub
            db.commit()
            db.refresh(user)
        return user

    user = User(
        email=email,
        full_name=full_name,
        role=_default_role(),
        auth_provider="oidc",
        external_id=sub,
        hashed_password=None,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
