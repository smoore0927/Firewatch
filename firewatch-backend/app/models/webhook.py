"""Webhook subscription + delivery ORM models."""

import enum

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import relationship

from app.models.database import Base

__all__ = ["WebhookSubscription", "WebhookDelivery", "DeliveryStatus"]


class DeliveryStatus(str, enum.Enum):
    pending = "pending"
    success = "success"
    failed = "failed"


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    target_url = Column(String(2000), nullable=False)
    # JSON list of event-type strings the subscriber wants to receive.
    event_types = Column(JSON, nullable=False)
    # Fernet-encrypted HMAC secret (see app/core/crypto.py).
    secret = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    last_delivered_at = Column(DateTime(timezone=True), nullable=True)
    consecutive_failures = Column(Integer, nullable=False, default=0, server_default="0")

    created_by = relationship("User")
    deliveries = relationship(
        "WebhookDelivery",
        back_populates="subscription",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<WebhookSubscription id={self.id} name={self.name}>"


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id = Column(Integer, primary_key=True)
    subscription_id = Column(
        Integer,
        ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # UUID hex without dashes; matches envelope["id"] minus the evt_ prefix length-wise.
    event_id = Column(String(40), nullable=False, index=True)
    event_type = Column(String(80), nullable=False)
    payload_json = Column(Text, nullable=False)
    status = Column(
        Enum(DeliveryStatus, name="webhookdeliverystatus"),
        nullable=False,
        default=DeliveryStatus.pending,
        index=True,
    )
    attempt_count = Column(Integer, nullable=False, default=0, server_default="0")
    http_status = Column(Integer, nullable=True)
    response_body = Column(String(1024), nullable=True)
    error = Column(String(1024), nullable=True)
    # When the next retry should run. NULL once terminal.
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    subscription = relationship("WebhookSubscription", back_populates="deliveries")

    def __repr__(self) -> str:
        return f"<WebhookDelivery id={self.id} sub={self.subscription_id} status={self.status}>"
