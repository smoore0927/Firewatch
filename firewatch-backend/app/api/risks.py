"""
Risk CRUD routes.

Route → Service pattern:
  Routes are deliberately thin here — they validate input (Pydantic does this
  automatically), call the service, and return a response. Business rules and
  database logic live in RiskService, which makes them testable independently.

RBAC summary:
  GET  /risks, GET /risks/:id     — any authenticated user (scope enforced in service)
  POST /risks                     — admin, security_analyst, risk_owner
  PUT  /risks/:id                 — any authenticated user (service checks ownership)
  POST /risks/:id/assessments     — any authenticated user (service checks ownership)
  POST /risks/:id/treatments      — any authenticated user (service checks ownership)
  DELETE /risks/:id               — admin only
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db, require_role
from app.models.risk import RiskStatus
from app.models.user import User, UserRole
from app.schemas.risk import (
    AssessmentCreate,
    RiskCreate,
    RiskListResponse,
    RiskResponse,
    RiskUpdate,
    TreatmentCreate,
)
from app.services.risk_service import RiskService

router = APIRouter(prefix="/risks", tags=["Risks"])


@router.get("", response_model=RiskListResponse)
def list_risks(
    status_filter: Optional[RiskStatus] = Query(None, alias="status"),
    category: Optional[str] = Query(None),
    owner_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RiskListResponse:
    service = RiskService(db)
    result = service.list_risks(
        current_user=current_user,
        status_filter=status_filter,
        category=category,
        owner_id=owner_id,
        skip=skip,
        limit=limit,
    )
    return RiskListResponse(**result)


@router.post(
    "",
    response_model=RiskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_risk(
    risk_data: RiskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.admin, UserRole.security_analyst, UserRole.risk_owner)
    ),
) -> RiskResponse:
    return RiskService(db).create_risk(risk_data=risk_data, created_by=current_user)


@router.get("/{risk_id}", response_model=RiskResponse)
def get_risk(
    risk_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RiskResponse:
    return RiskService(db).get_risk(risk_id=risk_id)


@router.put("/{risk_id}", response_model=RiskResponse)
def update_risk(
    risk_id: str,
    risk_data: RiskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RiskResponse:
    return RiskService(db).update_risk(
        risk_id=risk_id, risk_data=risk_data, updated_by=current_user
    )


@router.post("/{risk_id}/assessments", response_model=RiskResponse)
def add_assessment(
    risk_id: str,
    data: AssessmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RiskResponse:
    """Add a new scoring assessment to an existing risk."""
    return RiskService(db).add_assessment(
        risk_id=risk_id, data=data, assessed_by=current_user
    )


@router.post("/{risk_id}/treatments", response_model=RiskResponse)
def add_treatment(
    risk_id: str,
    data: TreatmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RiskResponse:
    """Add a mitigation/treatment plan to a risk."""
    return RiskService(db).add_treatment(
        risk_id=risk_id, data=data, created_by=current_user
    )


@router.delete("/{risk_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_risk(
    risk_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
) -> None:
    """Soft-delete a risk. Admin only. The record is retained for audit purposes."""
    RiskService(db).delete_risk(risk_id=risk_id)
