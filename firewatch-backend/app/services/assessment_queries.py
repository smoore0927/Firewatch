"""Assessment query helpers shared by the dashboard and analytics services."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from app.models.risk import Risk, RiskAssessment


def latest_assessment_ids(db: Session):
    """Subquery of (risk_id, assessment_id), one row per risk: its latest assessment.

    Ranks with the same ordering as the `Risk.assessments` relationship
    (assessed_at desc, id desc), so it picks the row the API reports as current.
    Joining on max(assessed_at) instead returns two rows when a risk's last two
    assessments share a timestamp -- easy on SQLite, whose CURRENT_TIMESTAMP has
    1-second resolution -- and every aggregate then counts that risk twice.
    """
    ranked = db.query(
        RiskAssessment.risk_id.label("risk_id"),
        RiskAssessment.id.label("assessment_id"),
        func.row_number()
        .over(
            partition_by=RiskAssessment.risk_id,
            order_by=(RiskAssessment.assessed_at.desc(), RiskAssessment.id.desc()),
        )
        .label("rn"),
    ).subquery()
    return (
        db.query(ranked.c.risk_id, ranked.c.assessment_id)
        .filter(ranked.c.rn == 1)
        .subquery()
    )


def with_current_score(query: Query, db: Session):
    """Outer-join `query` to each risk's latest assessment, returning (query, current_score_expr).

    current_score_expr matches app.core.severity.current_score exactly: the
    residual score when set, else the inherent score, else NULL (unscored).
    """
    latest = latest_assessment_ids(db)
    query = query.outerjoin(latest, latest.c.risk_id == Risk.id).outerjoin(
        RiskAssessment, RiskAssessment.id == latest.c.assessment_id
    )
    current_score_expr = func.coalesce(
        RiskAssessment.residual_risk_score, RiskAssessment.risk_score
    )
    return query, current_score_expr
