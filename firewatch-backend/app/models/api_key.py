"""ApiKey ORM model — user-scoped bearer credentials for API access."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base

__all__ = ["ApiKey"]


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(120), nullable=False)
    # First 8 url-safe chars after the fwk_ prefix; used as an indexed lookup
    # key so we don't have to scan/hash every row on every authenticated request.
    prefix = Column(String(16), nullable=False, index=True)
    # sha256 hex digest of the full plaintext (including the fwk_ prefix).
    hashed_key = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    owner = relationship("User", backref="api_keys")

    def __repr__(self) -> str:
        return f"<ApiKey id={self.id} user_id={self.user_id} prefix={self.prefix}>"
