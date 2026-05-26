"""Per-user in-app notification ORM model."""

from __future__ import annotations

import enum

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import relationship

from app.models.database import Base

__all__ = ["Notification", "NotificationType"]


class NotificationType(str, enum.Enum):
    risk_assigned = "risk_assigned"
    review_overdue = "review_overdue"
    response_overdue = "response_overdue"
    risk_changed = "risk_changed"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type = Column(
        Enum(NotificationType, name="notificationtype"),
        nullable=False,
    )
    # Nullable: aggregated events (e.g. review_overdue digest) reference many risks.
    risk_id = Column(Integer, ForeignKey("risks.id", ondelete="SET NULL"), nullable=True)
    payload = Column(JSON, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    read_at = Column(DateTime(timezone=True), nullable=True)
    dedup_key = Column(String(255), nullable=True, index=True)

    user = relationship("User")
    risk = relationship("Risk")

    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "read_at"),
        Index("ix_notifications_user_created", "user_id", "created_at"),
        # Partial unique index — Postgres + SQLite both support partial indexes.
        Index(
            "uq_notifications_user_dedup",
            "user_id",
            "dedup_key",
            unique=True,
            sqlite_where=text("dedup_key IS NOT NULL"),
            postgresql_where=text("dedup_key IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Notification id={self.id} user={self.user_id} type={self.type}>"
