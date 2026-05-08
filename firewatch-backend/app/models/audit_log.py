"""AuditLog ORM model — system-wide security event log."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base

__all__ = ["AuditLog"]


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    # Nullable: pre-auth events (failed login) have no resolved user.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # Denormalized snapshot — survives user deletion and records attempted email on failed logins.
    user_email = Column(String(255), nullable=True)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(50), nullable=True)
    # String so it works for both numeric IDs and human IDs like RISK-001.
    resource_id = Column(String(100), nullable=True)
    # IPv6-safe length.
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    # JSON-encoded extra context. Text for SQLite/Postgres portability.
    details = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} action={self.action} user_id={self.user_id}>"
