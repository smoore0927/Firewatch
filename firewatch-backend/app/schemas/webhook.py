"""Webhook subscription + delivery Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


# Single source of truth for the event-type vocabulary. Adding a new event type
# means adding it here, then emitting it from the producing service. The router
# rejects unknown values via this Literal at the Pydantic layer.
WebhookEventType = Literal[
    "risk.assigned",
    "review.overdue",
    "response.overdue",
    "firewatch.test",
]


class WebhookSubscriptionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_url: HttpUrl
    event_types: list[WebhookEventType] = Field(min_length=1)


class WebhookSubscriptionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    target_url: HttpUrl | None = None
    event_types: list[WebhookEventType] | None = Field(default=None, min_length=1)
    is_active: bool | None = None


class WebhookSubscriptionResponse(BaseModel):
    id: int
    name: str
    target_url: str
    event_types: list[str]
    is_active: bool
    created_at: datetime
    last_delivered_at: datetime | None
    consecutive_failures: int
    created_by_id: int

    model_config = ConfigDict(from_attributes=True)


class WebhookSubscriptionCreatedResponse(WebhookSubscriptionResponse):
    # Plaintext HMAC secret — shown exactly once on create, never returned again.
    secret: str


class WebhookDeliveryResponse(BaseModel):
    id: int
    event_id: str
    event_type: str
    status: str
    attempt_count: int
    http_status: int | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class WebhookDeliveryListResponse(BaseModel):
    total: int
    items: list[WebhookDeliveryResponse]
