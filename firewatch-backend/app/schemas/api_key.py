"""API key request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    expires_in_days: int | None = Field(default=None, ge=1, le=365)


class ApiKeyResponse(BaseModel):
    id: int
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None

    model_config = {"from_attributes": True}


class ApiKeyCreatedResponse(ApiKeyResponse):
    # Plaintext key — returned exactly once at creation, never again.
    key: str


class ApiKeyOwnerSummary(BaseModel):
    id: int
    email: str
    full_name: str | None

    model_config = {"from_attributes": True}


class ApiKeyWithOwnerResponse(ApiKeyResponse):
    owner: ApiKeyOwnerSummary
