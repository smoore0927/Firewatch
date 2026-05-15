from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.analytics import (
    ResidualReductionResponse,
    VelocityMTTMResponse,
    VelocityThroughputResponse,
)
from app.services.analytics_service import (
    build_mttm,
    build_residual_reduction,
    build_throughput,
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/velocity/mean-time-to-mitigation")
def get_mean_time_to_mitigation(
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    severity: Annotated[Optional[Literal["critical", "high", "medium", "low"]], Query()] = None,
    category: Annotated[Optional[str], Query()] = None,
) -> VelocityMTTMResponse:
    return build_mttm(db, start, end, severity, category)


@router.get("/velocity/throughput")
def get_throughput(
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    severity: Annotated[Optional[Literal["critical", "high", "medium", "low"]], Query()] = None,
    category: Annotated[Optional[str], Query()] = None,
) -> VelocityThroughputResponse:
    return build_throughput(db, start, end, severity, category)


@router.get("/velocity/residual-reduction")
def get_residual_reduction(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    severity: Annotated[Optional[Literal["critical", "high", "medium", "low"]], Query()] = None,
    category: Annotated[Optional[str], Query()] = None,
) -> ResidualReductionResponse:
    return build_residual_reduction(db, severity, category)
