"""
Risk request/response schemas.

Three request shapes:
  RiskCreate  — all fields for a new risk; likelihood/impact optional at creation
  RiskUpdate  — all fields optional (PATCH semantics — only send what changed)
  AssessmentCreate — add a new scoring assessment to an existing risk

Three response shapes:
  AssessmentResponse — a single scoring row
  RiskResponse       — full risk with its assessment history
  RiskListResponse   — paginated list with total count for the frontend
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.models.risk import RiskStatus, TreatmentStatus, TreatmentType


# ---------------------------------------------------------------------------
# Assessment schemas
# ---------------------------------------------------------------------------

class AssessmentCreate(BaseModel):
    likelihood: int = Field(..., ge=1, le=5)
    impact: int = Field(..., ge=1, le=5)
    residual_likelihood: Optional[int] = Field(None, ge=1, le=5)
    residual_impact: Optional[int] = Field(None, ge=1, le=5)
    notes: Optional[str] = None


class AssessmentResponse(BaseModel):
    id: int
    likelihood: int
    impact: int
    risk_score: int
    residual_likelihood: Optional[int]
    residual_impact: Optional[int]
    residual_risk_score: Optional[int]
    notes: Optional[str]
    assessed_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Treatment schemas
# ---------------------------------------------------------------------------

class TreatmentCreate(BaseModel):
    treatment_type: TreatmentType
    mitigation_strategy: str = Field(..., min_length=1)
    owner_id: Optional[int] = None
    start_date: Optional[datetime] = None
    target_date: Optional[datetime] = None
    cost_estimate: Optional[Decimal] = None
    notes: Optional[str] = None


class TreatmentResponse(BaseModel):
    id: int
    treatment_type: TreatmentType
    mitigation_strategy: str
    owner_id: Optional[int]
    start_date: Optional[datetime]
    target_date: Optional[datetime]
    completion_date: Optional[datetime]
    status: TreatmentStatus
    cost_estimate: Optional[Decimal]
    notes: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Risk schemas
# ---------------------------------------------------------------------------

class RiskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    threat_source: Optional[str] = None
    threat_event: Optional[str] = None
    vulnerability: Optional[str] = None
    affected_asset: Optional[str] = None
    category: Optional[str] = None
    owner_id: Optional[int] = None          # defaults to the creating user if omitted
    # Inline initial assessment — optional at creation, can be added later
    likelihood: Optional[int] = Field(None, ge=1, le=5)
    impact: Optional[int] = Field(None, ge=1, le=5)


class RiskUpdate(BaseModel):
    """
    All fields are Optional so callers send only what changed.
    model_dump(exclude_unset=True) in the service layer ensures we only
    update columns that were actually included in the request body.
    """
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    threat_source: Optional[str] = None
    threat_event: Optional[str] = None
    vulnerability: Optional[str] = None
    affected_asset: Optional[str] = None
    category: Optional[str] = None
    owner_id: Optional[int] = None
    status: Optional[RiskStatus] = None
    # Sending likelihood or impact creates a new RiskAssessment row
    likelihood: Optional[int] = Field(None, ge=1, le=5)
    impact: Optional[int] = Field(None, ge=1, le=5)


class RiskOwnerSummary(BaseModel):
    """Minimal owner info embedded in RiskResponse — avoids a second API call."""
    id: int
    email: str
    full_name: Optional[str]

    model_config = {"from_attributes": True}


class HistoryResponse(BaseModel):
    """One row from risk_history — a single field change at a point in time."""
    id: int
    field_changed: str
    old_value: Optional[str]
    new_value: Optional[str]
    changed_by_id: int
    changed_at: datetime

    model_config = {"from_attributes": True}


class RiskResponse(BaseModel):
    id: int
    risk_id: str
    title: str
    description: Optional[str]
    threat_source: Optional[str]
    threat_event: Optional[str]
    vulnerability: Optional[str]
    affected_asset: Optional[str]
    category: Optional[str]
    status: RiskStatus
    owner_id: int
    owner: Optional[RiskOwnerSummary] = None   # populated via SQLAlchemy relationship
    created_by_id: int
    created_at: datetime
    updated_at: Optional[datetime]
    # Full assessment history — frontend uses [0] for the current score
    assessments: list[AssessmentResponse] = []
    treatments: list[TreatmentResponse] = []
    # Field-level change log — every status change, re-score, etc.
    history: list[HistoryResponse] = []

    model_config = {"from_attributes": True}


class RiskListResponse(BaseModel):
    total: int                      # total matching records (for pagination UI)
    items: list[RiskResponse]
