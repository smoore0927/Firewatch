"""Integration tests for /api/analytics/velocity/*."""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.risk import Risk, RiskAssessment, RiskStatus
from app.models.user import User


def _seed_assessed_risk(db, *, owner: User, risk_id: str, assessments: list[dict]) -> Risk:
    risk = Risk(
        risk_id=risk_id,
        title=risk_id,
        owner_id=owner.id,
        created_by_id=owner.id,
        status=RiskStatus.open,
    )
    db.add(risk)
    db.flush()
    for fields in assessments:
        db.add(RiskAssessment(risk_id=risk.id, assessed_by_id=owner.id, **fields))
    db.commit()
    return risk


def test_residual_reduction_buckets_by_inherent_severity(client, admin_user, login_as, db):
    # Inherent 25 brought down to residual 4: the reduction is reported under
    # Critical, where the risk started, not Low, where it ended up.
    _seed_assessed_risk(db, owner=admin_user, risk_id="RISK-001", assessments=[
        {"likelihood": 5, "impact": 5, "risk_score": 25,
         "residual_likelihood": 2, "residual_impact": 2, "residual_risk_score": 4},
    ])

    login_as(admin_user)
    body = client.get("/api/analytics/velocity/residual-reduction").json()
    assert body["count"] == 1
    assert body["by_severity"]["critical"] == 21.0
    assert body["by_severity"]["low"] is None

    critical = client.get("/api/analytics/velocity/residual-reduction?severity=critical").json()
    assert critical["count"] == 1
    low = client.get("/api/analytics/velocity/residual-reduction?severity=low").json()
    assert low["count"] == 0


def test_residual_reduction_counts_a_risk_once_when_assessments_tie(
    client, admin_user, login_as, db
):
    # SQLite timestamps have 1-second resolution, so two quick assessments can
    # tie. Only the later row (higher id) is the risk's current assessment.
    same_instant = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
    _seed_assessed_risk(db, owner=admin_user, risk_id="RISK-001", assessments=[
        {"likelihood": 4, "impact": 4, "risk_score": 16,
         "residual_likelihood": 4, "residual_impact": 2, "residual_risk_score": 8,
         "assessed_at": same_instant},
        {"likelihood": 5, "impact": 5, "risk_score": 25,
         "residual_likelihood": 2, "residual_impact": 2, "residual_risk_score": 4,
         "assessed_at": same_instant},
    ])

    login_as(admin_user)
    body = client.get("/api/analytics/velocity/residual-reduction").json()
    assert body["count"] == 1
    assert body["avg_absolute"] == 21.0
