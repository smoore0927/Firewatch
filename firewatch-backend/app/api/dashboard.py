from __future__ import annotations

from datetime import date, datetime

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db
from app.models.risk import Risk, RiskAssessment, RiskTreatment, RiskStatus, TreatmentStatus
from app.models.user import User
from app.schemas.dashboard import DashboardSummaryResponse, ScoreHistoryPoint, ScoreHistoryResponse

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary")
def get_dashboard_summary(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> DashboardSummaryResponse:
    total = db.query(func.count(Risk.id)).filter(Risk.deleted_at.is_(None)).scalar()

    status_rows = (
        db.query(Risk.status, func.count(Risk.id))
        .filter(Risk.deleted_at.is_(None))
        .group_by(Risk.status)
        .all()
    )
    by_status: dict[str, int] = {
        "open": 0,
        "in_progress": 0,
        "mitigated": 0,
        "accepted": 0,
        "closed": 0,
    }
    for status, count in status_rows:
        by_status[status.value] = count

    latest_assessed_at = (
        db.query(
            RiskAssessment.risk_id,
            func.max(RiskAssessment.assessed_at).label("latest"),
        )
        .group_by(RiskAssessment.risk_id)
        .subquery()
    )
    matrix_rows = (
        db.query(
            RiskAssessment.likelihood,
            RiskAssessment.impact,
            func.count(Risk.id).label("cnt"),
        )
        .join(
            latest_assessed_at,
            (RiskAssessment.risk_id == latest_assessed_at.c.risk_id)
            & (RiskAssessment.assessed_at == latest_assessed_at.c.latest),
        )
        .join(Risk, Risk.id == RiskAssessment.risk_id)
        .filter(Risk.deleted_at.is_(None))
        .group_by(RiskAssessment.likelihood, RiskAssessment.impact)
        .all()
    )
    by_severity: dict[str, int] = {
        "Critical": 0,
        "High": 0,
        "Medium": 0,
        "Low": 0,
        "Unscored": 0,
    }
    risk_matrix: list[list[int]] = [[0] * 5 for _ in range(5)]

    for likelihood, impact, count in matrix_rows:
        risk_matrix[likelihood - 1][impact - 1] = count
        score = likelihood * impact
        if score <= 5:
            by_severity["Low"] += count
        elif score <= 12:
            by_severity["Medium"] += count
        elif score <= 20:
            by_severity["High"] += count
        else:
            by_severity["Critical"] += count

    scored_risk_ids = db.query(RiskAssessment.risk_id).distinct()
    by_severity["Unscored"] = (
        db.query(func.count(Risk.id))
        .filter(Risk.deleted_at.is_(None))
        .filter(Risk.id.not_in(scored_risk_ids))
        .scalar()
    )

    overdue_treatments = (
        db.query(func.count(RiskTreatment.id))
        .filter(RiskTreatment.target_date.isnot(None))
        .filter(RiskTreatment.target_date < date.today())
        .filter(RiskTreatment.status != TreatmentStatus.completed)
        .scalar()
    )

    overdue_reviews = (
        db.query(func.count(Risk.id))
        .filter(Risk.deleted_at.is_(None))
        .filter(Risk.next_review_date.isnot(None))
        .filter(Risk.next_review_date <= date.today())
        .filter(Risk.status.notin_([RiskStatus.closed, RiskStatus.mitigated]))
        .scalar()
    )

    return DashboardSummaryResponse(
        total=total,
        by_status=by_status,
        by_severity=by_severity,
        overdue_treatments=overdue_treatments,
        overdue_reviews=overdue_reviews,
        risk_matrix=risk_matrix,
    )


@router.get("/score-history")
def get_score_history(
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ScoreHistoryResponse:
    start_dt = datetime(start.year, start.month, start.day)
    end_dt = datetime(end.year, end.month, end.day, 23, 59, 59)

    rows = (
        db.query(
            func.date(RiskAssessment.assessed_at).label("day"),
            func.avg(RiskAssessment.risk_score).label("avg_score"),
            func.count(RiskAssessment.id).label("cnt"),
        )
        .join(Risk, Risk.id == RiskAssessment.risk_id)
        .filter(Risk.deleted_at.is_(None))
        .filter(RiskAssessment.assessed_at >= start_dt)
        .filter(RiskAssessment.assessed_at <= end_dt)
        .group_by(func.date(RiskAssessment.assessed_at))
        .order_by(func.date(RiskAssessment.assessed_at))
        .all()
    )

    return ScoreHistoryResponse(
        points=[
            ScoreHistoryPoint(date=str(row.day), avg_score=round(row.avg_score, 1), count=row.cnt)
            for row in rows
        ]
    )
