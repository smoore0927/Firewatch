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

import secrets
from typing import Generator
from datetime import timezone

from fastapi import Cookie, Depends, HTTPException, Request, status
from jwt import PyJWTError as JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_token
from app.models.database import SessionLocal
from app.models.user import User, UserRole


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


def get_current_user(
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    """
    Read the access_token HTTP-only cookie, decode the JWT, and return the User.
    Raises 401 if the cookie is missing, the token is expired/invalid, or the
    user no longer exists or is deactivated.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )
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

    last_logout = user.last_logout_at
    if last_logout is not None:
        # iat is a Unix timestamp (int); last_logout_at is timezone-aware datetime
        token_iat = payload.get("iat", 0)
        logout_ts = last_logout.replace(tzinfo=timezone.utc).timestamp() if last_logout.tzinfo is None else last_logout.timestamp()
        if token_iat < logout_ts:
            raise credentials_exception

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
