"""
Schemas for authentication endpoints.

Pydantic validates every field before your route handler runs.
If email is malformed or password is empty, FastAPI returns a 422 automatically
— you never write validation boilerplate in your route.
"""

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr     # validates format: "user@example.com", rejects "notanemail"
    password: str


class LoginResponse(BaseModel):
    """Returned after a successful login. Tokens are in HTTP-only cookies, not here."""
    user_id: int
    email: str
    role: str
    full_name: str | None
