"""
User request/response schemas.

Why separate Create/Response instead of one User schema?
  - UserCreate includes 'password' (plain text, write-only).
  - UserResponse includes 'hashed_password'... no it doesn't — it never exposes
    the hash. Having separate schemas makes it impossible to accidentally leak
    the hash in a response, even if you copy-paste carelessly.
"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=12)   # enforce a minimum password length
    full_name: str | None = None
    role: UserRole = UserRole.risk_owner


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str | None
    role: UserRole
    is_active: bool
    created_at: datetime

    # from_attributes=True tells Pydantic to read values from SQLAlchemy model
    # attributes rather than expecting a plain dict. Required for ORM integration.
    model_config = {"from_attributes": True}
