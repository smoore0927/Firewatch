"""SCIM 2.0 user provisioning logic — translates between SCIM payloads and User rows."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User, UserRole
from app.schemas.scim import (
    SCIMEmail,
    SCIMMeta,
    SCIMName,
    SCIMPatchOp,
    SCIMUser,
)


class SCIMConflictError(Exception):
    """A SCIM resource already exists (uniqueness violation)."""


class SCIMInvalidFilterError(Exception):
    """The SCIM filter expression is unsupported or malformed."""


class SCIMNotFoundError(Exception):
    """No SCIM resource matched the given id."""


def _split_name(full_name: str | None) -> tuple[str | None, str | None]:
    """Split a display name on the first space into given/family components."""
    if not full_name:
        return None, None
    parts = full_name.strip().split(" ", 1)
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]


def user_to_scim(user: User, base_url: str) -> SCIMUser:
    """Build a SCIMUser resource from a User row."""
    given, family = _split_name(user.full_name)
    created = user.created_at or datetime.now(timezone.utc)
    last_modified = user.updated_at or created
    base = base_url.rstrip("/")
    return SCIMUser(
        id=str(user.id),
        externalId=user.external_id,
        userName=user.email,
        name=SCIMName(givenName=given, familyName=family),
        emails=[SCIMEmail(value=user.email, primary=True, type="work")],
        active=bool(user.is_active),
        meta=SCIMMeta(
            resourceType="User",
            created=created,
            lastModified=last_modified,
            location=f"{base}/api/scim/v2/Users/{user.id}",
        ),
    )


def _name_to_full_name(name: SCIMName | None) -> str | None:
    if name is None:
        return None
    parts = [p for p in (name.givenName, name.familyName) if p]
    if not parts:
        return None
    return " ".join(parts).strip()


def create_user_from_scim(db: Session, payload: SCIMUser) -> User:
    """Create a User from a SCIM payload. Raises SCIMConflictError on duplicate email."""
    if not payload.userName:
        raise SCIMConflictError("userName is required")

    existing = db.query(User).filter(User.email == payload.userName).first()
    if existing:
        raise SCIMConflictError("A user with that userName already exists")

    full_name = _name_to_full_name(payload.name)
    user = User(
        email=payload.userName,
        external_id=payload.externalId,
        auth_provider="oidc",
        hashed_password=None,
        is_active=payload.active,
        role=UserRole(settings.OIDC_DEFAULT_ROLE),
        full_name=full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def replace_user_from_scim(db: Session, user: User, payload: SCIMUser) -> User:
    """Replace all writable fields on an existing user from a SCIM payload."""
    new_active = bool(payload.active)
    if user.is_active and not new_active:
        user.last_logout_at = datetime.now(timezone.utc)

    user.email = payload.userName
    user.external_id = payload.externalId
    user.full_name = _name_to_full_name(payload.name)
    user.is_active = new_active
    db.commit()
    db.refresh(user)
    return user


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


def _apply_attr(user: User, attr: str, value: Any) -> bool:
    """Apply a single attribute set. Returns True if 'active' changed to False."""
    lowered = attr.lower()
    deactivated = False

    if lowered == "active":
        new_active = _coerce_bool(value)
        if user.is_active and not new_active:
            deactivated = True
        user.is_active = new_active
    elif lowered == "username":
        if value is not None:
            user.email = value
    elif lowered == "externalid":
        user.external_id = value
    elif lowered == "name.givenname":
        _, family = _split_name(user.full_name)
        given = value or ""
        user.full_name = " ".join(p for p in (given, family) if p).strip() or None
    elif lowered == "name.familyname":
        given, _ = _split_name(user.full_name)
        family = value or ""
        user.full_name = " ".join(p for p in (given, family) if p).strip() or None
    elif lowered == "name":
        if isinstance(value, dict):
            given = value.get("givenName") or value.get("givenname")
            family = value.get("familyName") or value.get("familyname")
            user.full_name = " ".join(p for p in (given, family) if p).strip() or None
    elif re.fullmatch(r"emails\[primary\s+eq\s+true\]\.value", lowered):
        if value is not None:
            user.email = value
    elif lowered == "emails":
        # Find the primary email in the list (or fall back to first entry).
        if isinstance(value, list) and value:
            primary = next((e for e in value if e.get("primary")), value[0])
            email_val = primary.get("value") if isinstance(primary, dict) else None
            if email_val:
                user.email = email_val
    return deactivated


def apply_patch_ops(db: Session, user: User, ops: list[SCIMPatchOp]) -> User:
    """Apply a list of SCIM PATCH operations to a user."""
    any_deactivation = False

    for op in ops:
        op_name = op.op.lower()
        path = op.path
        value = op.value

        if not path:
            # Path-less op: value must be a dict of attributes to merge
            if isinstance(value, dict):
                for attr, attr_val in value.items():
                    if _apply_attr(user, attr, attr_val):
                        any_deactivation = True
            continue

        if op_name == "remove":
            if path.lower() == "active":
                if user.is_active:
                    any_deactivation = True
                user.is_active = False
            elif path.lower() == "externalid":
                user.external_id = None
            # Other remove targets are silently ignored.
            continue

        # add / replace
        if _apply_attr(user, path, value):
            any_deactivation = True

    if any_deactivation:
        user.last_logout_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(user)
    return user


_FILTER_RE = re.compile(
    r'^\s*(?P<attr>[A-Za-z_][A-Za-z0-9_]*)\s+eq\s+"(?P<value>[^"]*)"\s*$'
)


def parse_scim_filter(filter_str: str | None) -> dict | None:
    """Parse the minimal `attr eq "value"` filter Entra sends. None means no filter."""
    if filter_str is None or not filter_str.strip():
        return None
    match = _FILTER_RE.match(filter_str)
    if not match:
        raise SCIMInvalidFilterError(f"Unsupported filter: {filter_str!r}")

    attr_raw = match.group("attr")
    value = match.group("value")
    lowered = attr_raw.lower()
    if lowered == "username":
        return {"attr": "userName", "value": value}
    if lowered == "externalid":
        return {"attr": "externalId", "value": value}
    raise SCIMInvalidFilterError(f"Unsupported filter attribute: {attr_raw!r}")
