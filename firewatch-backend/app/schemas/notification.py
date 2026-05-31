"""In-app notification request/response schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_serializer

from app.schemas._datetime import serialize_utc_datetime


class NotificationType(str, Enum):
    risk_assigned = "risk_assigned"
    review_overdue = "review_overdue"
    response_overdue = "response_overdue"
    risk_changed = "risk_changed"


class NotificationResponse(BaseModel):
    id: int
    type: NotificationType
    risk_id: int | None
    risk_human_id: str | None
    title: str
    message: str
    link: str
    created_at: datetime
    read_at: datetime | None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at")
    def _ser_created_at(self, dt: datetime) -> str:
        return serialize_utc_datetime(dt)

    @field_serializer("read_at")
    def _ser_datetimes(self, dt: datetime | None) -> str | None:
        return serialize_utc_datetime(dt)


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    unread_total: int


class UnreadCountResponse(BaseModel):
    count: int


class MarkAllReadResponse(BaseModel):
    marked: int
