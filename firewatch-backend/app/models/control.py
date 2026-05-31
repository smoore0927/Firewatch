"""Compliance control framework mapping models.

Three tables:
  ControlFramework (1) ──< Control          — a framework and its catalogue of controls
  Risk (M) ──< RiskControl >── Control (M)   — many-to-many mapping of risks to controls
"""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship

from app.models.database import Base

__all__ = ["ControlFramework", "Control", "RiskControl", "DeletedFrameworkSeed"]


class ControlFramework(Base):
    __tablename__ = "control_frameworks"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    version = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    source_url = Column(String(1000), nullable=True)
    last_imported_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    controls = relationship("Control", back_populates="framework", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ControlFramework {self.name}>"


class Control(Base):
    __tablename__ = "controls"

    id = Column(Integer, primary_key=True)
    framework_id = Column(Integer, ForeignKey("control_frameworks.id"), nullable=False, index=True)
    control_id = Column(String(100), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    family = Column(String(255), nullable=True)

    framework = relationship("ControlFramework", back_populates="controls")

    __table_args__ = (
        UniqueConstraint("framework_id", "control_id", name="uq_controls_framework_control"),
    )

    def __repr__(self) -> str:
        return f"<Control {self.control_id}>"


class RiskControl(Base):
    __tablename__ = "risk_controls"

    id = Column(Integer, primary_key=True)
    risk_id = Column(Integer, ForeignKey("risks.id"), nullable=False, index=True)
    control_id = Column(Integer, ForeignKey("controls.id"), nullable=False, index=True)
    # "mitigates" | "monitors" | "detects"
    mapping_type = Column(String(50), nullable=False, default="mitigates")
    notes = Column(Text, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    risk = relationship("Risk", back_populates="controls")
    control = relationship("Control")
    created_by = relationship("User")

    __table_args__ = (
        UniqueConstraint("risk_id", "control_id", name="uq_risk_controls_risk_control"),
    )

    def __repr__(self) -> str:
        return f"<RiskControl risk={self.risk_id} control={self.control_id}>"


class DeletedFrameworkSeed(Base):
    """Tombstone for seeded frameworks an admin deleted, so the seed won't re-create them."""

    __tablename__ = "deleted_framework_seeds"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    deleted_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    deleted_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    def __repr__(self) -> str:
        return f"<DeletedFrameworkSeed {self.name}>"
