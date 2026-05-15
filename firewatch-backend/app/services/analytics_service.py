"""Risk velocity analytics — mean-time-to-mitigation, throughput, residual reduction."""

from __future__ import annotations

import statistics
from datetime import date, datetime, time, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.risk import Risk, RiskAssessment, RiskHistory
from app.schemas.analytics import (
    ResidualReductionBySeverity,
    ResidualReductionResponse,
    VelocityMTTMBySeverity,
    VelocityMTTMResponse,
    VelocityThroughputPoint,
    VelocityThroughputResponse,
)


_SEVERITY_KEYS = ("critical", "high", "medium", "low")


def _severity_for_score(score: int) -> str:
    """Map a risk_score to a severity bucket using the dashboard convention."""
    if score <= 5:
        return "low"
    if score <= 12:
        return "medium"
    if score <= 20:
        return "high"
    return "critical"


def _avg_or_none(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _latest_assessment_subquery(db: Session):
    return (
        db.query(
            RiskAssessment.risk_id,
            func.max(RiskAssessment.assessed_at).label("latest"),
        )
        .group_by(RiskAssessment.risk_id)
        .subquery()
    )


def _first_closure_subquery(db: Session):
    """Per-risk subquery returning the earliest history row marking closure."""
    return (
        db.query(
            RiskHistory.risk_id,
            func.min(RiskHistory.changed_at).label("closed_at"),
        )
        .filter(RiskHistory.field_changed == "status")
        .filter(RiskHistory.new_value.in_(("mitigated", "closed")))
        .group_by(RiskHistory.risk_id)
        .subquery()
    )


def _severity_score_filter(severity: str):
    """Returns a SQLAlchemy clause filtering RiskAssessment.risk_score by severity bucket."""
    if severity == "low":
        return RiskAssessment.risk_score <= 5
    if severity == "medium":
        return (RiskAssessment.risk_score > 5) & (RiskAssessment.risk_score <= 12)
    if severity == "high":
        return (RiskAssessment.risk_score > 12) & (RiskAssessment.risk_score <= 20)
    return RiskAssessment.risk_score > 20  # critical


def build_mttm(
    db: Session,
    start: date,
    end: date,
    severity: str | None = None,
    category: str | None = None,
) -> VelocityMTTMResponse:
    start_dt = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end, time.max, tzinfo=timezone.utc)

    closure = _first_closure_subquery(db)
    latest = _latest_assessment_subquery(db)

    query = db.query(
        Risk.id,
        Risk.created_at,
        closure.c.closed_at,
        RiskAssessment.risk_score,
    ).join(closure, closure.c.risk_id == Risk.id)

    if severity is not None:
        query = query.join(latest, latest.c.risk_id == Risk.id).join(
            RiskAssessment,
            (RiskAssessment.risk_id == latest.c.risk_id)
            & (RiskAssessment.assessed_at == latest.c.latest),
        )
    else:
        query = query.outerjoin(latest, latest.c.risk_id == Risk.id).outerjoin(
            RiskAssessment,
            (RiskAssessment.risk_id == latest.c.risk_id)
            & (RiskAssessment.assessed_at == latest.c.latest),
        )

    query = (
        query.filter(Risk.deleted_at.is_(None))
        .filter(closure.c.closed_at >= start_dt)
        .filter(closure.c.closed_at <= end_dt)
    )

    if category is not None:
        query = query.filter(Risk.category == category)
    if severity is not None:
        query = query.filter(_severity_score_filter(severity))

    rows = query.all()

    all_deltas: list[float] = []
    by_severity_deltas: dict[str, list[float]] = {k: [] for k in _SEVERITY_KEYS}

    for _risk_id, created_at, closed_at, risk_score in rows:
        delta_days = (closed_at - created_at).total_seconds() / 86400.0
        all_deltas.append(delta_days)
        if risk_score is not None:
            bucket = _severity_for_score(risk_score)
            by_severity_deltas[bucket].append(delta_days)

    mean_days = _avg_or_none(all_deltas)
    median_days = round(statistics.median(all_deltas), 1) if all_deltas else None

    return VelocityMTTMResponse(
        mean_days=mean_days,
        median_days=median_days,
        count=len(all_deltas),
        by_severity=VelocityMTTMBySeverity(
            critical=_avg_or_none(by_severity_deltas["critical"]),
            high=_avg_or_none(by_severity_deltas["high"]),
            medium=_avg_or_none(by_severity_deltas["medium"]),
            low=_avg_or_none(by_severity_deltas["low"]),
        ),
    )


def _months_in_range(start: date, end: date) -> list[str]:
    """Inclusive list of YYYY-MM strings from start month through end month."""
    months: list[str] = []
    year, month = start.year, start.month
    end_year, end_month = end.year, end.month
    while (year, month) <= (end_year, end_month):
        months.append(f"{year:04d}-{month:02d}")
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    return months


def build_throughput(
    db: Session,
    start: date,
    end: date,
    severity: str | None = None,
    category: str | None = None,
) -> VelocityThroughputResponse:
    start_dt = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end, time.max, tzinfo=timezone.utc)

    opened_query = (
        db.query(Risk.created_at)
        .filter(Risk.deleted_at.is_(None))
        .filter(Risk.created_at >= start_dt)
        .filter(Risk.created_at <= end_dt)
    )
    if category is not None:
        opened_query = opened_query.filter(Risk.category == category)
    if severity is not None:
        latest_opened = _latest_assessment_subquery(db)
        opened_query = (
            opened_query.join(latest_opened, latest_opened.c.risk_id == Risk.id)
            .join(
                RiskAssessment,
                (RiskAssessment.risk_id == latest_opened.c.risk_id)
                & (RiskAssessment.assessed_at == latest_opened.c.latest),
            )
            .filter(_severity_score_filter(severity))
        )
    opened_rows = opened_query.all()

    closure = _first_closure_subquery(db)
    closed_query = (
        db.query(closure.c.closed_at)
        .join(Risk, Risk.id == closure.c.risk_id)
        .filter(Risk.deleted_at.is_(None))
        .filter(closure.c.closed_at >= start_dt)
        .filter(closure.c.closed_at <= end_dt)
    )
    if category is not None:
        closed_query = closed_query.filter(Risk.category == category)
    if severity is not None:
        latest_closed = _latest_assessment_subquery(db)
        closed_query = (
            closed_query.join(latest_closed, latest_closed.c.risk_id == Risk.id)
            .join(
                RiskAssessment,
                (RiskAssessment.risk_id == latest_closed.c.risk_id)
                & (RiskAssessment.assessed_at == latest_closed.c.latest),
            )
            .filter(_severity_score_filter(severity))
        )
    closed_rows = closed_query.all()

    opened_counts: dict[str, int] = {}
    for (created_at,) in opened_rows:
        key = f"{created_at.year:04d}-{created_at.month:02d}"
        opened_counts[key] = opened_counts.get(key, 0) + 1

    closed_counts: dict[str, int] = {}
    for (closed_at,) in closed_rows:
        key = f"{closed_at.year:04d}-{closed_at.month:02d}"
        closed_counts[key] = closed_counts.get(key, 0) + 1

    points = [
        VelocityThroughputPoint(
            period=month,
            opened=opened_counts.get(month, 0),
            closed=closed_counts.get(month, 0),
        )
        for month in _months_in_range(start, end)
    ]

    return VelocityThroughputResponse(points=points)


def build_residual_reduction(
    db: Session,
    severity: str | None = None,
    category: str | None = None,
) -> ResidualReductionResponse:
    latest = _latest_assessment_subquery(db)

    query = (
        db.query(RiskAssessment.risk_score, RiskAssessment.residual_risk_score)
        .join(
            latest,
            (RiskAssessment.risk_id == latest.c.risk_id)
            & (RiskAssessment.assessed_at == latest.c.latest),
        )
        .join(Risk, Risk.id == RiskAssessment.risk_id)
        .filter(Risk.deleted_at.is_(None))
        .filter(RiskAssessment.risk_score.isnot(None))
        .filter(RiskAssessment.residual_risk_score.isnot(None))
    )

    if category is not None:
        query = query.filter(Risk.category == category)
    if severity is not None:
        query = query.filter(_severity_score_filter(severity))

    rows = query.all()

    absolutes: list[float] = []
    percentages: list[float] = []
    by_severity_abs: dict[str, list[float]] = {k: [] for k in _SEVERITY_KEYS}

    for risk_score, residual in rows:
        absolute = float(risk_score - residual)
        percentage = (absolute / risk_score) * 100.0 if risk_score else 0.0
        absolutes.append(absolute)
        percentages.append(percentage)
        by_severity_abs[_severity_for_score(risk_score)].append(absolute)

    return ResidualReductionResponse(
        avg_absolute=_avg_or_none(absolutes),
        avg_percentage=_avg_or_none(percentages),
        count=len(absolutes),
        by_severity=ResidualReductionBySeverity(
            critical=_avg_or_none(by_severity_abs["critical"]),
            high=_avg_or_none(by_severity_abs["high"]),
            medium=_avg_or_none(by_severity_abs["medium"]),
            low=_avg_or_none(by_severity_abs["low"]),
        ),
    )
