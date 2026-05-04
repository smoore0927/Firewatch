"""Schemas for authentication endpoints."""

from datetime import datetime

from pydantic import BaseModel


class LoginRequest(BaseModel):
    # str instead of EmailStr: avoids 422 vs 401 distinction that enables email enumeration.
    # The login handler queries the DB (returns None for malformed input) and always returns
    # a uniform 401 for all failure cases.
    email: str
    password: str


class LoginResponse(BaseModel):
    """Returned after a successful login. Tokens are in HTTP-only cookies, not here."""
    user_id: int
    email: str
    role: str
    full_name: str | None
    is_active: bool
    created_at: datetime
