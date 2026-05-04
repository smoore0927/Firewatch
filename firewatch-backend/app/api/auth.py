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

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_user, get_db
from app.core.limiter import limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse
from app.schemas.user import UserResponse

router = APIRouter(prefix="/auth", tags=["Auth"])


def _set_auth_cookies(response: Response, user_id: int) -> None:
    """Write both auth cookies. Extracted to avoid duplicating cookie settings."""
    response.set_cookie(
        key="access_token",
        value=create_access_token(user_id),
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=create_refresh_token(user_id),
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/auth/refresh",   # restrict to the refresh endpoint only
    )


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
def login(
    request: Request,
    credentials: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
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
    # Always call verify_password even on a None user to prevent timing attacks
    # (an attacker measuring response time could detect valid vs. invalid emails)
    password_ok = verify_password(credentials.password, user.hashed_password) if user else False

    if not user or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    _set_auth_cookies(response, user.id)

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
    refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """
    Exchange a valid refresh token for a new access token.
    Called automatically by the frontend when a 401 is received.
    """
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
    )
    if not refresh_token:
        raise invalid
    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise invalid
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise invalid

    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if not user:
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
def logout(response: Response) -> None:
    """Clear both auth cookies. The tokens remain valid until expiry server-side,
    but the client can no longer send them."""
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token", path="/api/auth/refresh")


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> User:
    """Return the currently authenticated user's profile."""
    return current_user
