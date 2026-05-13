"""
User request/response schemas.

Why separate Create/Response instead of one User schema?
  - UserCreate includes 'password' (plain text, write-only).
  - UserResponse includes 'hashed_password'... no it doesn't — it never exposes
    the hash. Having separate schemas makes it impossible to accidentally leak
    the hash in a response, even if you copy-paste carelessly.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, field_validator, model_validator

from app.models.user import UserRole
from app.schemas._password_policy import validate_password_complexity


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    role: UserRole = UserRole.risk_owner

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        return validate_password_complexity(value)


class RoleUpdateRequest(BaseModel):
    role: UserRole


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str | None
    role: UserRole
    is_active: bool
    created_at: datetime
    has_password: bool
    must_change_password: bool

    # from_attributes=True tells Pydantic to read values from SQLAlchemy model
    # attributes rather than expecting a plain dict. Required for ORM integration.
    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _derive_has_password(cls, data: Any) -> Any:
        # Derive has_password from the User ORM object's hashed_password attribute
        # when constructing from an ORM instance via from_attributes.
        if isinstance(data, dict):
            if "has_password" not in data and "hashed_password" in data:
                data = {**data, "has_password": data["hashed_password"] is not None}
            return data
        if hasattr(data, "hashed_password"):
            # Build a dict that preserves all ORM attributes plus the derived flag.
            return {
                "id": data.id,
                "email": data.email,
                "full_name": data.full_name,
                "role": data.role,
                "is_active": data.is_active,
                "created_at": data.created_at,
                "has_password": data.hashed_password is not None,
                "must_change_password": getattr(data, "must_change_password", False),
            }
        return data
