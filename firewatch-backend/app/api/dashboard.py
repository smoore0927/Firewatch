from __future__ import annotations

from datetime import date

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db
from app.core.roles import UserRole
from app.models.user import User
from app.schemas.dashboard import (
    ActionQueueResponse,
    DashboardSummaryResponse,
    ScoreHistoryResponse,
    ScoreTotalsBySeverityResponse,
)
from app.services.dashboard_service import (
    build_action_queue,
    build_score_history,
    build_score_totals_by_severity,
    build_summary,
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _scope_owner_id(user: User) -> int | None:
    """Return the user's id when they should be scoped to their own risks, else None."""
    return user.id if user.role == UserRole.risk_owner else None


@router.get("/summary")
def get_dashboard_summary(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> DashboardSummaryResponse:
    return build_summary(db, scope_owner_id=_scope_owner_id(current_user))


@router.get("/score-history")
def get_score_history(
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ScoreHistoryResponse:
    return build_score_history(db, start, end, scope_owner_id=_scope_owner_id(current_user))


@router.get("/score-totals-by-severity")
def get_score_totals_by_severity(
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ScoreTotalsBySeverityResponse:
    return build_score_totals_by_severity(
        db, start, end, scope_owner_id=_scope_owner_id(current_user)
    )


@router.get("/action-queue")
def get_action_queue(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> ActionQueueResponse:
    return build_action_queue(db, scope_owner_id=_scope_owner_id(current_user), limit=limit)
