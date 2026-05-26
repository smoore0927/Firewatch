"""Pydantic schemas for the system-wide audit log."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_serializer

from app.schemas._datetime import serialize_utc_datetime


class AuditLogResponse(BaseModel):
    id: int
    user_id: int | None
    user_email: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    ip_address: str | None
    user_agent: str | None
    details: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at")
    def _ser_created_at(self, dt: datetime) -> str | None:
        return serialize_utc_datetime(dt)


class AuditLogListResponse(BaseModel):
    total: int
    items: list[AuditLogResponse]


class AuditActionsResponse(BaseModel):
    actions: list[str]
