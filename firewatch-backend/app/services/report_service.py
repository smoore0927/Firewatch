"""Build the consolidated risk-report payload used by the frontend PDF exporter."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.core.roles import UserRole
from app.core.severity import current_likelihood_impact, current_score, severity_for_score
from app.models.user import User
from app.schemas.report import (
    ReportDateRange,
    ReportUserRef,
    RiskReportResponse,
    RiskReportRow,
)
from app.services.dashboard_service import build_score_history, build_summary
from app.services.risk_service import RiskService


_SEVERITY_RANK = {
    "Critical": 4,
    "High": 3,
    "Medium": 2,
    "Low": 1,
    "Unscored": 0,
}


def _classify(score: int | None) -> str:
    severity = severity_for_score(score)
    return severity.capitalize() if severity else "Unscored"


def _build_risk_rows(db: Session, user: User) -> list[RiskReportRow]:
    # Reuse RiskService.list_risks so role-based scoping has exactly one home.
    result = RiskService(db).list_risks(current_user=user, skip=0, limit=10000)
    risks = result["items"]

    rows: list[RiskReportRow] = []
    for risk in risks:
        # Risk.assessments is ordered (assessed_at desc, id desc) — first row is latest.
        # "Current" means residual when assessed, matching the register and dashboard.
        latest = risk.assessments[0] if risk.assessments else None
        likelihood, impact = current_likelihood_impact(latest) or (None, None)
        score = current_score(latest)

        owner_name: str | None = None
        if risk.owner is not None:
            owner_name = risk.owner.full_name or risk.owner.email

        rows.append(RiskReportRow(
            id=risk.id,
            title=risk.title,
            category=risk.category,
            status=risk.status.value,
            current_likelihood=likelihood,
            current_impact=impact,
            current_score=score,
            severity=_classify(score),
            owner_name=owner_name,
            next_review_date=risk.next_review_date,
        ))

    rows.sort(
        key=lambda r: (
            -_SEVERITY_RANK[r.severity],
            -(r.current_score if r.current_score is not None else -1),
            r.id,
        )
    )
    return rows


def build_risk_report(
    db: Session,
    user: User,
    start: date,
    end: date,
    include_risks: bool,
) -> RiskReportResponse:
    # Scope the aggregates exactly like the dashboard endpoints: a risk owner's
    # report must not carry org-wide totals for risks they cannot see.
    scope_owner_id = user.id if user.role == UserRole.risk_owner else None
    summary = build_summary(db, scope_owner_id=scope_owner_id)
    score_history = build_score_history(db, start, end, scope_owner_id=scope_owner_id)
    risks = _build_risk_rows(db, user) if include_risks else None

    return RiskReportResponse(
        generated_at=datetime.now(timezone.utc),
        generated_by=ReportUserRef(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role.value,
        ),
        date_range=ReportDateRange(start=start, end=end),
        summary=summary,
        score_history=score_history,
        risks=risks,
    )
