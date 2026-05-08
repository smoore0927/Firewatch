from __future__ import annotations

from datetime import date

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.dashboard import (
    DashboardSummaryResponse,
    ScoreHistoryResponse,
    ScoreTotalsBySeverityResponse,
)
from app.services.dashboard_service import (
    build_score_history,
    build_score_totals_by_severity,
    build_summary,
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary")
def get_dashboard_summary(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> DashboardSummaryResponse:
    return build_summary(db)


@router.get("/score-history")
def get_score_history(
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ScoreHistoryResponse:
    return build_score_history(db, start, end)


@router.get("/score-totals-by-severity")
def get_score_totals_by_severity(
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ScoreTotalsBySeverityResponse:
    return build_score_totals_by_severity(db, start, end)
