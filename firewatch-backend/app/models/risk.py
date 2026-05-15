"""
Risk register models — four tables that together represent a complete NIST 800-30 risk entry.

Table relationships:
  Risk (1) ──< RiskAssessment  — scoring history; latest row = current score
  Risk (1) ──< RiskResponse    — response/mitigation plans; many responses per risk
  Risk (1) ──< RiskHistory     — field-level change log for audit trail

Why separate RiskAssessment instead of columns on Risk?
  If likelihood or impact were columns on risks, updating them would overwrite
  the previous values. A separate table records every assessment so you can
  answer "how has this risk's score changed over the past 6 months?" — a
  compliance requirement for NIST 800-30 programmes.

Soft delete on Risk:
  Setting deleted_at instead of issuing DELETE preserves all linked assessments,
  responses, and history rows. Required for audit trail completeness.
"""

import enum

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RiskStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    mitigated = "mitigated"
    accepted = "accepted"
    closed = "closed"


class ResponseType(str, enum.Enum):
    """The four NIST-standard risk response strategies."""
    mitigate = "mitigate"    # reduce likelihood or impact via controls
    accept = "accept"        # acknowledge and accept the risk as-is
    transfer = "transfer"    # shift risk to a third party (insurance, vendor)
    avoid = "avoid"          # eliminate the activity that causes the risk


class ResponseStatus(str, enum.Enum):
    planned = "planned"
    in_progress = "in_progress"
    completed = "completed"
    deferred = "deferred"


# ---------------------------------------------------------------------------
# Risk — core record
# ---------------------------------------------------------------------------

class Risk(Base):
    __tablename__ = "risks"

    id = Column(Integer, primary_key=True)
    # Human-readable identifier shown in the UI and reports (RISK-001, RISK-002, ...)
    risk_id = Column(String(20), unique=True, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text)

    # NIST 800-30 fields — "what is the risk?"
    threat_source = Column(String(255))    # e.g. "External adversary", "Insider threat"
    threat_event = Column(String(500))     # e.g. "Phishing attack targeting credentials"
    vulnerability = Column(Text)           # e.g. "No MFA on admin accounts"
    affected_asset = Column(String(500))   # e.g. "Customer PII database"
    category = Column(String(100))         # e.g. "Technical", "Compliance", "Operational"

    status = Column(Enum(RiskStatus), nullable=False, default=RiskStatus.open, index=True)

    # How often the risk should be reassessed (days). NULL = no scheduled cadence.
    review_frequency_days = Column(Integer, nullable=True)
    # The next date this risk is due for reassessment; indexed for dashboard/list filters.
    next_review_date = Column(Date, nullable=True, index=True)

    # Two FKs to users — owner is responsible for the risk, created_by logged it.
    # Specifying foreign_keys on the relationship is required when two FKs point
    # at the same table; otherwise SQLAlchemy cannot resolve the ambiguity.
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    # NULL = active record; non-NULL = soft-deleted
    deleted_at = Column(DateTime(timezone=True))

    # Relationships
    owner = relationship("User", foreign_keys=[owner_id], back_populates="owned_risks")
    created_by = relationship("User", foreign_keys=[created_by_id], back_populates="created_risks")

    # order_by ensures .assessments[0] is always the most recent assessment.
    # Tiebreak on id desc because SQLite's CURRENT_TIMESTAMP has 1-second resolution
    # and two assessments in the same second would otherwise sort non-deterministically.
    assessments = relationship(
        "RiskAssessment",
        back_populates="risk",
        order_by="(RiskAssessment.assessed_at.desc(), RiskAssessment.id.desc())",
        cascade="all, delete-orphan",
    )
    responses = relationship(
        "RiskResponse",
        back_populates="risk",
        cascade="all, delete-orphan",
    )
    history = relationship(
        "RiskHistory",
        back_populates="risk",
        # Tiebreak on id desc — see assessments order_by note above.
        order_by="(RiskHistory.changed_at.desc(), RiskHistory.id.desc())",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Risk {self.risk_id} status={self.status}>"


# ---------------------------------------------------------------------------
# RiskAssessment — one row per scoring event
# ---------------------------------------------------------------------------

class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id = Column(Integer, primary_key=True)
    risk_id = Column(Integer, ForeignKey("risks.id"), nullable=False, index=True)

    # 1-5 scale: 1=Very Low, 2=Low, 3=Moderate, 4=High, 5=Very High
    likelihood = Column(Integer, nullable=False)
    impact = Column(Integer, nullable=False)
    # Stored (not computed on-the-fly) so historical records remain accurate
    # even if the formula ever changes. Range: 1 (1x1) to 25 (5x5).
    risk_score = Column(Integer, nullable=False)

    # Residual fields — the score after planned/implemented controls are accounted for
    residual_likelihood = Column(Integer)
    residual_impact = Column(Integer)
    residual_risk_score = Column(Integer)

    notes = Column(Text)
    assessed_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assessed_at = Column(DateTime(timezone=True), server_default=text('CURRENT_TIMESTAMP'), nullable=False)

    risk = relationship("Risk", back_populates="assessments")
    assessed_by = relationship("User")


# ---------------------------------------------------------------------------
# RiskResponse — risk response / mitigation plan
# ---------------------------------------------------------------------------

class RiskResponse(Base):
    __tablename__ = "risk_responses"

    id = Column(Integer, primary_key=True)
    risk_id = Column(Integer, ForeignKey("risks.id"), nullable=False, index=True)

    # Enum type names on disk remain `treatmenttype` / `treatmentstatus` for
    # PostgreSQL backwards compatibility — only the Python class names changed.
    # On SQLite these are stored as VARCHAR + CHECK so the name is unused.
    response_type = Column(Enum(ResponseType, name="treatmenttype"), nullable=False)
    mitigation_strategy = Column(Text, nullable=False)

    owner_id = Column(Integer, ForeignKey("users.id"))
    start_date = Column(Date)
    target_date = Column(Date)
    completion_date = Column(Date)
    status = Column(
        Enum(ResponseStatus, name="treatmentstatus"),
        nullable=False,
        default=ResponseStatus.planned,
    )

    # Numeric(12, 2) stores dollar amounts without floating-point rounding errors
    cost_estimate = Column(Numeric(12, 2))
    notes = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    risk = relationship("Risk", back_populates="responses")
    owner = relationship("User")


# ---------------------------------------------------------------------------
# RiskHistory — field-level audit trail
# ---------------------------------------------------------------------------

class RiskHistory(Base):
    """
    One row per changed field per update. The risk service compares old and new
    values and writes a row for each difference, giving you a full timeline:
      "On 2025-03-14, Sam changed 'status' from 'open' to 'in_progress'"
    """
    __tablename__ = "risk_history"

    id = Column(Integer, primary_key=True)
    risk_id = Column(Integer, ForeignKey("risks.id"), nullable=False, index=True)

    field_changed = Column(String(100), nullable=False)
    old_value = Column(Text)   # NULL = field was not previously set
    new_value = Column(Text)   # NULL = field was cleared

    changed_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    changed_at = Column(DateTime(timezone=True), server_default=text('CURRENT_TIMESTAMP'), nullable=False)

    risk = relationship("Risk", back_populates="history")
    changed_by = relationship("User")
