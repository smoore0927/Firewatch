"""Unit tests for app/core/severity.py — the one place severity cut-offs live."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.severity import (
    current_likelihood_impact,
    current_score,
    severity_clause,
    severity_for_score,
)
from app.models.risk import Risk, RiskAssessment, RiskStatus


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (None, None),
        (1, "low"),
        (5, "low"),
        (6, "medium"),
        (12, "medium"),
        (13, "high"),
        (20, "high"),
        (21, "critical"),
        (25, "critical"),
    ],
)
def test_severity_for_score_bucket_edges(score, expected):
    assert severity_for_score(score) == expected


def _assessment(**overrides) -> SimpleNamespace:
    fields = {
        "likelihood": 5,
        "impact": 4,
        "risk_score": 20,
        "residual_likelihood": None,
        "residual_impact": None,
        "residual_risk_score": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_current_score_prefers_residual_score():
    assert current_score(None) is None
    assert current_score(_assessment()) == 20
    residual = _assessment(residual_likelihood=2, residual_impact=3, residual_risk_score=6)
    assert current_score(residual) == 6


def test_current_likelihood_impact_uses_residual_only_when_both_are_set():
    assert current_likelihood_impact(None) is None
    assert current_likelihood_impact(_assessment()) == (5, 4)
    residual = _assessment(residual_likelihood=2, residual_impact=3, residual_risk_score=6)
    assert current_likelihood_impact(residual) == (2, 3)
    assert current_likelihood_impact(_assessment(residual_likelihood=2)) == (5, 4)


def test_severity_clause_agrees_with_severity_for_score(db, admin_user):
    """The SQL filter and the Python mapping must bucket every score identically."""
    risk = Risk(
        risk_id="RISK-001",
        title="Every score",
        owner_id=admin_user.id,
        created_by_id=admin_user.id,
        status=RiskStatus.open,
    )
    db.add(risk)
    db.flush()
    for score in range(1, 26):
        db.add(RiskAssessment(
            risk_id=risk.id,
            likelihood=1,
            impact=1,
            risk_score=score,
            assessed_by_id=admin_user.id,
        ))
    db.commit()

    for severity in ("low", "medium", "high", "critical"):
        matched = {
            score
            for (score,) in db.query(RiskAssessment.risk_score).filter(
                severity_clause(RiskAssessment.risk_score, severity)
            )
        }
        assert matched == {s for s in range(1, 26) if severity_for_score(s) == severity}
