"""User-scoped API key management routes.

Admins and security analysts can mint API keys against their own user account.
Created keys authenticate API requests on behalf of the creating user, with
that user's role/permissions. Keys are sent in the Authorization header as
`Bearer fwk_<token>`; the authentication wiring lives in core/dependencies.py.
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, require_role
from app.models.api_key import ApiKey
from app.models.user import User, UserRole
from app.schemas.api_key import (
    ApiKeyCreate,
    ApiKeyCreatedResponse,
    ApiKeyResponse,
    ApiKeyWithOwnerResponse,
)
from app.services import api_key_service
from app.services.audit_service import record_event

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


@router.get("")
def list_api_keys(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        User, Depends(require_role(UserRole.admin, UserRole.security_analyst))
    ],
) -> list[ApiKeyResponse]:
    """List the calling user's API keys (no plaintext returned)."""
    rows = api_key_service.list_for_user(db, user_id=current_user.id)
    return [ApiKeyResponse.model_validate(r) for r in rows]


@router.get("/all", response_model=list[ApiKeyWithOwnerResponse])
def list_all_api_keys(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_role(UserRole.admin))],
) -> list[ApiKey]:
    """Admin-only: every API key in the system, with owner info."""
    return api_key_service.list_all(db)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_api_key(
    request: Request,
    body: ApiKeyCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        User, Depends(require_role(UserRole.admin, UserRole.security_analyst))
    ],
) -> ApiKeyCreatedResponse:
    """Create a new API key for the calling user. Plaintext is shown ONCE."""
    expires_at: datetime | None = None
    if body.expires_in_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_in_days)

    row, plaintext = api_key_service.create(
        db,
        user_id=current_user.id,
        name=body.name,
        expires_at=expires_at,
    )

    record_event(
        db,
        action="apikey.created",
        user=current_user,
        resource_type="api_key",
        resource_id=str(row.id),
        request=request,
        details={
            "name": row.name,
            "prefix": row.prefix,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        },
    )
    db.commit()

    return ApiKeyCreatedResponse(
        id=row.id,
        name=row.name,
        prefix=row.prefix,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        key=plaintext,
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    request: Request,
    key_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        User, Depends(require_role(UserRole.admin, UserRole.security_analyst))
    ],
) -> None:
    """Revoke a key. Owners self-serve; admins can revoke any key."""
    key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    # Don't distinguish "doesn't exist" from "owned by someone else" for
    # non-admins — avoids leaking the existence of other users' key IDs.
    is_admin = current_user.role == UserRole.admin
    if key is None or (not is_admin and key.user_id != current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="API key not found"
        )

    if key.revoked_at is not None:
        # Already revoked — return 204 idempotently without writing another audit row.
        return

    details: dict = {"name": key.name, "prefix": key.prefix}
    if is_admin and key.user_id != current_user.id:
        details["revoked_by_admin"] = True
        details["target_user_email"] = key.owner.email if key.owner else None

    api_key_service.revoke(db, key)
    record_event(
        db,
        action="apikey.revoked",
        user=current_user,
        resource_type="api_key",
        resource_id=str(key.id),
        request=request,
        details=details,
    )
    db.commit()
