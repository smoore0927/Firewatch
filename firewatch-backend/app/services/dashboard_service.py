"""Reusable dashboard query helpers used by both /api/dashboard and /api/reports."""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.risk import Risk, RiskAssessment, RiskResponse, RiskStatus, ResponseStatus
from app.schemas.dashboard import (
    DashboardSummaryResponse,
    ScoreHistoryPoint,
    ScoreHistoryResponse,
    ScoreTotalsBySeverityPoint,
    ScoreTotalsBySeverityResponse,
)


def build_summary(
    db: Session,
    *,
    scope_owner_id: int | None = None,
) -> DashboardSummaryResponse:
    total_q = db.query(func.count(Risk.id)).filter(Risk.deleted_at.is_(None))
    if scope_owner_id is not None:
        total_q = total_q.filter(Risk.owner_id == scope_owner_id)
    total = total_q.scalar()

    status_q = (
        db.query(Risk.status, func.count(Risk.id))
        .filter(Risk.deleted_at.is_(None))
    )
    if scope_owner_id is not None:
        status_q = status_q.filter(Risk.owner_id == scope_owner_id)
    status_rows = status_q.group_by(Risk.status).all()
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
    matrix_q = (
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
    )
    if scope_owner_id is not None:
        matrix_q = matrix_q.filter(Risk.owner_id == scope_owner_id)
    matrix_rows = matrix_q.group_by(RiskAssessment.likelihood, RiskAssessment.impact).all()
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

    if scope_owner_id is not None:
        scored_risk_ids = (
            db.query(RiskAssessment.risk_id)
            .join(Risk, Risk.id == RiskAssessment.risk_id)
            .filter(Risk.owner_id == scope_owner_id)
            .distinct()
        )
    else:
        scored_risk_ids = db.query(RiskAssessment.risk_id).distinct()
    unscored_q = (
        db.query(func.count(Risk.id))
        .filter(Risk.deleted_at.is_(None))
        .filter(Risk.id.not_in(scored_risk_ids))
    )
    if scope_owner_id is not None:
        unscored_q = unscored_q.filter(Risk.owner_id == scope_owner_id)
    by_severity["Unscored"] = unscored_q.scalar()

    overdue_responses_q = (
        db.query(func.count(RiskResponse.id))
        .filter(RiskResponse.target_date.isnot(None))
        .filter(RiskResponse.target_date < date.today())
        .filter(RiskResponse.status != ResponseStatus.completed)
    )
    if scope_owner_id is not None:
        overdue_responses_q = (
            overdue_responses_q.join(Risk, Risk.id == RiskResponse.risk_id)
            .filter(Risk.owner_id == scope_owner_id)
            .filter(Risk.deleted_at.is_(None))
        )
    overdue_responses = overdue_responses_q.scalar()

    overdue_reviews_q = (
        db.query(func.count(Risk.id))
        .filter(Risk.deleted_at.is_(None))
        .filter(Risk.next_review_date.isnot(None))
        .filter(Risk.next_review_date <= date.today())
        .filter(Risk.status.notin_([RiskStatus.closed, RiskStatus.mitigated]))
    )
    if scope_owner_id is not None:
        overdue_reviews_q = overdue_reviews_q.filter(Risk.owner_id == scope_owner_id)
    overdue_reviews = overdue_reviews_q.scalar()

    return DashboardSummaryResponse(
        total=total,
        by_status=by_status,
        by_severity=by_severity,
        overdue_responses=overdue_responses,
        overdue_reviews=overdue_reviews,
        risk_matrix=risk_matrix,
    )


def build_score_history(
    db: Session,
    start: date,
    end: date,
    *,
    scope_owner_id: int | None = None,
) -> ScoreHistoryResponse:
    start_dt = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end, time.max, tzinfo=timezone.utc)

    query = (
        db.query(
            func.date(RiskAssessment.assessed_at).label("day"),
            func.avg(RiskAssessment.risk_score).label("avg_score"),
            func.count(RiskAssessment.id).label("cnt"),
        )
        .join(Risk, Risk.id == RiskAssessment.risk_id)
        .filter(Risk.deleted_at.is_(None))
        .filter(RiskAssessment.assessed_at >= start_dt)
        .filter(RiskAssessment.assessed_at <= end_dt)
    )
    if scope_owner_id is not None:
        query = query.filter(Risk.owner_id == scope_owner_id)
    rows = (
        query.group_by(func.date(RiskAssessment.assessed_at))
        .order_by(func.date(RiskAssessment.assessed_at))
        .all()
    )

    return ScoreHistoryResponse(
        points=[
            ScoreHistoryPoint(date=str(row.day), avg_score=round(row.avg_score, 1), count=row.cnt)
            for row in rows
        ]
    )


def build_score_totals_by_severity(
    db: Session,
    start: date,
    end: date,
    *,
    scope_owner_id: int | None = None,
) -> ScoreTotalsBySeverityResponse:
    start_dt = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end, time.max, tzinfo=timezone.utc)

    low_sum = func.sum(case((RiskAssessment.risk_score <= 5, RiskAssessment.risk_score), else_=0))
    medium_sum = func.sum(
        case(
            ((RiskAssessment.risk_score > 5) & (RiskAssessment.risk_score <= 12),
             RiskAssessment.risk_score),
            else_=0,
        )
    )
    high_sum = func.sum(
        case(
            ((RiskAssessment.risk_score > 12) & (RiskAssessment.risk_score <= 20),
             RiskAssessment.risk_score),
            else_=0,
        )
    )
    critical_sum = func.sum(case((RiskAssessment.risk_score > 20, RiskAssessment.risk_score), else_=0))

    query = (
        db.query(
            func.date(RiskAssessment.assessed_at).label("day"),
            low_sum.label("low"),
            medium_sum.label("medium"),
            high_sum.label("high"),
            critical_sum.label("critical"),
        )
        .join(Risk, Risk.id == RiskAssessment.risk_id)
        .filter(Risk.deleted_at.is_(None))
        .filter(RiskAssessment.assessed_at >= start_dt)
        .filter(RiskAssessment.assessed_at <= end_dt)
    )
    if scope_owner_id is not None:
        query = query.filter(Risk.owner_id == scope_owner_id)
    rows = (
        query.group_by(func.date(RiskAssessment.assessed_at))
        .order_by(func.date(RiskAssessment.assessed_at))
        .all()
    )

    return ScoreTotalsBySeverityResponse(
        points=[
            ScoreTotalsBySeverityPoint(
                date=str(row.day),
                low=int(row.low or 0),
                medium=int(row.medium or 0),
                high=int(row.high or 0),
                critical=int(row.critical or 0),
            )
            for row in rows
        ]
    )
