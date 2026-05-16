"""
FastAPI dependency functions — injected into route handlers via Depends().

How FastAPI dependency injection works:
  Instead of calling get_db() or get_current_user() directly in your route,
  you declare them as parameters with Depends(). FastAPI calls them for you,
  handles cleanup (the finally block in get_db), and caches the result within
  a single request. This keeps route handlers thin and logic testable.

  Example:
    @router.get("/risks")
    def list_risks(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
        ...
"""

import logging
import secrets
from typing import Generator
from datetime import datetime, timezone

from fastapi import Cookie, Depends, HTTPException, Request, status
from jwt import PyJWTError as JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_token
from app.models.database import SessionLocal
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)


def get_db() -> Generator[Session, None, None]:
    """
    Yield a database session for the duration of a request, then close it.
    Using a generator ensures the session is always closed, even on errors.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_authenticated_user(
    request: Request,
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    """
    Read the access_token HTTP-only cookie, decode the JWT, and return the User.
    Raises 401 if the cookie is missing, the token is expired/invalid, or the
    user no longer exists or is deactivated.

    Also accepts an `Authorization: Bearer fwk_<token>` header for user-scoped
    API keys minted via /api/api-keys; on a match, returns that key's owner.
    The fwk_ prefix keeps these cleanly separable from SCIM bearer tokens
    (which use a different prefix and live behind require_scim_token).

    Private: this is the raw auth check with no first-login gate. Callers should
    almost always use get_current_user (which adds the PASSWORD_CHANGE_REQUIRED
    gate) instead. Use get_current_user_allow_password_pending only for the
    handful of routes the user legitimately needs while their flag is True
    (/me, /logout, /change-password).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )

    # --- API key path (Authorization: Bearer fwk_…) ----------------------
    # Imported lazily so this module doesn't pull api_key_service at import
    # time (avoids any risk of circular imports during app boot).
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer fwk_"):
        from app.services import api_key_service  # local import

        plaintext = auth_header[len("Bearer "):]
        key = api_key_service.lookup_by_plaintext(db, plaintext)
        if key is None:
            raise credentials_exception
        owner = key.owner
        if owner is None or not owner.is_active:
            raise credentials_exception

        # Best-effort last_used_at update; never break a request because we
        # couldn't bump this stat.
        try:
            key.last_used_at = datetime.now(timezone.utc)
            db.commit()
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to update api_key.last_used_at")
            db.rollback()

        return owner

    # --- Cookie path (default) -------------------------------------------
    if not access_token:
        raise credentials_exception

    try:
        payload = decode_token(access_token)
        if payload.get("type") != "access":
            # Reject if someone submits a refresh token where an access token is expected
            raise credentials_exception
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = (
        db.query(User)
        .filter(User.id == int(user_id), User.is_active.is_(True))
        .first()
    )
    if not user:
        raise credentials_exception

    token_sv = payload.get("sv")
    if token_sv != user.session_version:
        raise credentials_exception

    return user


def get_current_user(user: User = Depends(_get_authenticated_user)) -> User:
    """Authenticated user, gated on the first-login password change.

    Any route that uses this dependency (directly or via require_role) returns
    403 PASSWORD_CHANGE_REQUIRED while the user's must_change_password flag
    is set. The frontend should treat this as a signal to redirect into the
    /change-password flow.
    """
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="PASSWORD_CHANGE_REQUIRED",
        )
    return user


def get_current_user_allow_password_pending(
    user: User = Depends(_get_authenticated_user),
) -> User:
    """Authenticated user without the first-login gate.

    Use only on /me, /logout, and /change-password — the three routes the user
    legitimately needs while their must_change_password flag is True.
    """
    return user


def require_role(*roles: UserRole):
    """
    Factory that returns a dependency enforcing role-based access.

    Usage:
      @router.delete("/{id}", dependencies=[Depends(require_role(UserRole.admin))])
      — or —
      current_user: User = Depends(require_role(UserRole.admin, UserRole.security_analyst))

    Why a factory instead of a single function?
      Roles differ per endpoint. The factory captures the allowed roles at
      definition time so the returned dependency is specific to each route.
    """
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return role_checker


def require_scim_token(request: Request) -> None:
    """Validate the SCIM bearer token from the Authorization header (timing-safe)."""
    if not settings.SCIM_ENABLED or not settings.SCIM_BEARER_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SCIM_NOT_CONFIGURED",
        )

    header = request.headers.get("authorization") or ""
    expected_prefix = "Bearer "
    if not header.startswith(expected_prefix):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    presented = header[len(expected_prefix):]
    if not secrets.compare_digest(presented, settings.SCIM_BEARER_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        )
