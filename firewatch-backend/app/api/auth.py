"""
Authentication routes: login, token refresh, logout, and current-user.

Cookie security settings explained:
  httponly=True   — JavaScript cannot read this cookie (XSS protection).
                    The browser sends it automatically with every request.
  secure=True     — Cookie is only transmitted over HTTPS. Disabled in DEBUG
                    mode so localhost (HTTP) development still works.
  samesite="lax"  — Cookie is sent on same-site requests and top-level
                    navigations, but not on cross-site POST requests.
                    This prevents most CSRF attacks without needing a token.
  path="/api/auth/refresh" on the refresh cookie — the browser only sends the
                    refresh token to that one endpoint, not every API request.
                    If the access token is stolen, the attacker still can't
                    silently refresh it without also stealing the refresh cookie.
"""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from jwt import PyJWTError as JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_user, get_db
from app.core.limiter import limiter
from app.core.security import (
    create_access_token,
    decode_token,
    set_auth_cookies,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse
from app.schemas.user import UserResponse
from app.services.audit_service import record_event

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login")
@limiter.limit("5/minute")
def login(
    request: Request,
    credentials: LoginRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> LoginResponse:
    """
    Validate email + password. On success, write HTTP-only auth cookies
    and return the user's basic info (no token in the response body).
    """
    user = (
        db.query(User)
        .filter(User.email == credentials.email, User.is_active.is_(True))
        .first()
    )
    # SSO-only users have hashed_password=None — calling bcrypt on None would crash.
    # The combined guard keeps the unknown-email and SSO-only-user paths indistinguishable
    # from a wrong password, so timing/response shape doesn't leak account state.
    password_ok = (
        verify_password(credentials.password, user.hashed_password)
        if user and user.hashed_password
        else False
    )

    if not user or not password_ok:
        record_event(
            db,
            action="auth.login.failed",
            user_email=credentials.email,
            resource_type="auth",
            request=request,
            details={"reason": "invalid_credentials"},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    set_auth_cookies(response, user.id)
    record_event(
        db,
        action="auth.login.success",
        user=user,
        resource_type="auth",
        request=request,
        details={"method": "password"},
    )
    db.commit()

    return LoginResponse(
        user_id=user.id,
        email=user.email,
        role=user.role.value,
        full_name=user.full_name,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.post("/refresh")
@limiter.limit("30/minute")
def refresh(
    request: Request,
    response: Response,
    *,
    refresh_token: Annotated[str | None, Cookie()] = None,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """
    Exchange a valid refresh token for a new access token.
    Called automatically by the frontend when a 401 is received.
    """
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
    )

    def _record_failure(reason: str) -> None:
        record_event(
            db,
            action="auth.refresh.failed",
            resource_type="auth",
            request=request,
            details={"reason": reason},
        )
        db.commit()

    if not refresh_token:
        _record_failure("missing_token")
        raise invalid
    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            _record_failure("wrong_token_type")
            raise invalid
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        _record_failure("decode_error")
        raise invalid

    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if not user:
        _record_failure("user_not_found")
        raise invalid

    # Issue a fresh access token (not a new refresh token — avoids token rotation complexity)
    response.set_cookie(
        key="access_token",
        value=create_access_token(user.id),
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return {"message": "Token refreshed"}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Clear both auth cookies. The tokens remain valid until expiry server-side,
    but the client can no longer send them."""
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token", path="/api/auth/refresh")
    record_event(
        db,
        action="auth.logout",
        user=current_user,
        resource_type="auth",
        request=request,
    )
    db.commit()


@router.get("/me", response_model=UserResponse)
def get_me(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    """Return the currently authenticated user's profile."""
    return current_user
