"""Reusable dashboard query helpers used by both /api/dashboard and /api/reports."""

from __future__ import annotations

import bisect
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.risk import Risk, RiskAssessment, RiskHistory, RiskResponse, RiskStatus, ResponseStatus

_TERMINAL_STATUSES = {RiskStatus.mitigated, RiskStatus.accepted, RiskStatus.closed}
from app.schemas.dashboard import (
    ActionQueueItem,
    ActionQueueResponse,
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
    """Cumulative time-series of active-risk score totals bucketed by severity.

    For each day D in ``[start, end]`` we look at every visible, non-deleted risk
    and find its latest assessment with ``assessed_at <= end-of-D``. That score
    contributes to D's severity bucket. Risks whose status as of D was
    ``mitigated``, ``accepted``, or ``closed`` are skipped for that day (their
    status timeline is reconstructed from ``RiskHistory`` rows where
    ``field_changed == 'status'``). Risks with no assessment at-or-before D
    contribute nothing. One point per day is emitted, even when totals don't
    change day-over-day, so the chart can draw a smooth continuous line.
    """
    # 1. Pull all non-deleted risks visible to the caller (plus current status).
    risks_q = db.query(Risk.id, Risk.status).filter(Risk.deleted_at.is_(None))
    if scope_owner_id is not None:
        risks_q = risks_q.filter(Risk.owner_id == scope_owner_id)
    risk_rows = risks_q.all()
    risk_ids = [rid for (rid, _) in risk_rows]
    current_status_by_risk: dict[int, RiskStatus] = {rid: status for (rid, status) in risk_rows}

    # 2. Pull every assessment for those risks, ordered for grouping.
    #    Tiebreak on id so assessments in the same second are deterministic.
    assessments_by_risk: dict[int, list[tuple[datetime, int]]] = {}
    if risk_ids:
        rows = (
            db.query(
                RiskAssessment.risk_id,
                RiskAssessment.assessed_at,
                RiskAssessment.risk_score,
            )
            .filter(RiskAssessment.risk_id.in_(risk_ids))
            .order_by(RiskAssessment.risk_id, RiskAssessment.assessed_at, RiskAssessment.id)
            .all()
        )
        for risk_id, assessed_at, risk_score in rows:
            # SQLite drops tzinfo even with DateTime(timezone=True). Normalise
            # to UTC-aware so comparisons against the tz-aware end-of-day
            # boundary don't raise TypeError.
            if assessed_at.tzinfo is None:
                assessed_at = assessed_at.replace(tzinfo=timezone.utc)
            assessments_by_risk.setdefault(risk_id, []).append((assessed_at, risk_score))

    # Pre-extract the sorted timestamp keys per risk for bisect.
    timestamps_by_risk: dict[int, list[datetime]] = {
        rid: [ts for ts, _ in events] for rid, events in assessments_by_risk.items()
    }

    # 2b. Pull status-change history rows for those risks and group per-risk.
    status_history_by_risk: dict[int, list[tuple[datetime, str]]] = {}
    initial_status_by_risk: dict[int, str] = {}
    if risk_ids:
        history_rows = (
            db.query(
                RiskHistory.risk_id,
                RiskHistory.changed_at,
                RiskHistory.old_value,
                RiskHistory.new_value,
            )
            .filter(RiskHistory.risk_id.in_(risk_ids))
            .filter(RiskHistory.field_changed == "status")
            .order_by(RiskHistory.risk_id, RiskHistory.changed_at, RiskHistory.id)
            .all()
        )
        for risk_id, changed_at, old_value, new_value in history_rows:
            if changed_at.tzinfo is None:
                changed_at = changed_at.replace(tzinfo=timezone.utc)
            timeline = status_history_by_risk.setdefault(risk_id, [])
            if not timeline:
                # Earliest history row's old_value is the initial status.
                initial_status_by_risk[risk_id] = old_value
            timeline.append((changed_at, new_value))

    status_timestamps_by_risk: dict[int, list[datetime]] = {
        rid: [ts for ts, _ in events] for rid, events in status_history_by_risk.items()
    }

    def _status_at(rid: int, end_of_day: datetime) -> str:
        """Resolve the risk's status as of end-of-day D."""
        timeline = status_history_by_risk.get(rid)
        if not timeline:
            return current_status_by_risk[rid].value
        timestamps = status_timestamps_by_risk[rid]
        idx = bisect.bisect_right(timestamps, end_of_day) - 1
        if idx < 0:
            return initial_status_by_risk[rid]
        return timeline[idx][1]

    # 3. Emit one point per day, walking [start, end] inclusive.
    points: list[ScoreTotalsBySeverityPoint] = []
    current = start
    while current <= end:
        end_of_day = datetime.combine(current, time.max, tzinfo=timezone.utc)
        low = medium = high = critical = 0
        for rid, events in assessments_by_risk.items():
            # Skip risks that were in a terminal status as of this day.
            status_value = _status_at(rid, end_of_day)
            try:
                if RiskStatus(status_value) in _TERMINAL_STATUSES:
                    continue
            except ValueError:
                pass
            timestamps = timestamps_by_risk[rid]
            # Rightmost event with assessed_at <= end_of_day.
            idx = bisect.bisect_right(timestamps, end_of_day) - 1
            if idx < 0:
                continue
            score = events[idx][1]
            if score <= 5:
                low += score
            elif score <= 12:
                medium += score
            elif score <= 20:
                high += score
            else:
                critical += score
        points.append(
            ScoreTotalsBySeverityPoint(
                date=current.isoformat(),
                low=low,
                medium=medium,
                high=high,
                critical=critical,
            )
        )
        current += timedelta(days=1)

    return ScoreTotalsBySeverityResponse(points=points)


def build_action_queue(
    db: Session,
    *,
    scope_owner_id: int | None = None,
    limit: int = 20,
) -> ActionQueueResponse:
    today = date.today()

    reviews_q = (
        db.query(Risk.risk_id, Risk.title, Risk.next_review_date)
        .filter(Risk.deleted_at.is_(None))
        .filter(Risk.next_review_date.isnot(None))
        .filter(Risk.next_review_date <= today)
        .filter(Risk.status.notin_([RiskStatus.closed, RiskStatus.mitigated]))
    )
    if scope_owner_id is not None:
        reviews_q = reviews_q.filter(Risk.owner_id == scope_owner_id)
    review_rows = reviews_q.all()

    responses_q = (
        db.query(Risk.risk_id, Risk.title, RiskResponse.target_date)
        .join(Risk, Risk.id == RiskResponse.risk_id)
        .filter(Risk.deleted_at.is_(None))
        .filter(RiskResponse.target_date.isnot(None))
        .filter(RiskResponse.target_date < today)
        .filter(RiskResponse.status != ResponseStatus.completed)
    )
    if scope_owner_id is not None:
        responses_q = responses_q.filter(Risk.owner_id == scope_owner_id)
    response_rows = responses_q.all()

    items: list[ActionQueueItem] = []
    for risk_id, title, due in review_rows:
        items.append(ActionQueueItem(
            kind="review",
            risk_id=risk_id,
            risk_title=title,
            due_date=due.isoformat(),
            days_overdue=(today - due).days,
        ))
    for risk_id, title, due in response_rows:
        items.append(ActionQueueItem(
            kind="response",
            risk_id=risk_id,
            risk_title=title,
            due_date=due.isoformat(),
            days_overdue=(today - due).days,
        ))

    total = len(items)
    items.sort(key=lambda i: i.days_overdue, reverse=True)
    return ActionQueueResponse(items=items[:limit], total=total)
