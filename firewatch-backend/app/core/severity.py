"""
Single source of truth for risk-score severity.

A score is likelihood x impact on 1-5 scales, so 1-25. Every place that labels
a score Low / Medium / High / Critical (dashboard, reports, analytics, the risk
API) goes through here so the cut-offs can't drift apart. The frontend mirrors
these cut-offs in `scoreLabel` (src/types/index.ts); keep the two in step.

Two score bases are in use, on purpose:
  * current score -- the residual score when the latest assessment has one,
    otherwise the inherent score. Used for anything describing a risk's
    posture *now*: the risk API, dashboard summary and reports.
  * inherent score -- used by the velocity analytics, which measure how quickly
    risks get brought down. Bucketing those by residual score would file every
    mitigated risk under Low.
"""

from typing import Literal, Protocol

Severity = Literal["low", "medium", "high", "critical"]

# Inclusive upper bound of each bucket; anything above HIGH_MAX is critical.
LOW_MAX = 5
MEDIUM_MAX = 12
HIGH_MAX = 20


class _Assessment(Protocol):
    """Any assessment-shaped object: the ORM model or the Pydantic schema."""

    likelihood: int
    impact: int
    risk_score: int
    residual_likelihood: int | None
    residual_impact: int | None
    residual_risk_score: int | None


def severity_for_score(score: int | None) -> Severity | None:
    """Map a 1-25 score to its severity bucket. None (unscored) stays None."""
    if score is None:
        return None
    if score <= LOW_MAX:
        return "low"
    if score <= MEDIUM_MAX:
        return "medium"
    if score <= HIGH_MAX:
        return "high"
    return "critical"


def severity_clause(score_column, severity: Severity):
    """SQLAlchemy filter matching rows whose `score_column` is in `severity`."""
    if severity == "low":
        return score_column <= LOW_MAX
    if severity == "medium":
        return (score_column > LOW_MAX) & (score_column <= MEDIUM_MAX)
    if severity == "high":
        return (score_column > MEDIUM_MAX) & (score_column <= HIGH_MAX)
    return score_column > HIGH_MAX


def current_score(assessment: _Assessment | None) -> int | None:
    """The residual score when the assessment has one, else the inherent score."""
    if assessment is None:
        return None
    if assessment.residual_risk_score is not None:
        return assessment.residual_risk_score
    return assessment.risk_score


def current_likelihood_impact(assessment: _Assessment | None) -> tuple[int, int] | None:
    """(likelihood, impact) matching `current_score`: residual when both are set."""
    if assessment is None:
        return None
    if assessment.residual_likelihood is not None and assessment.residual_impact is not None:
        return assessment.residual_likelihood, assessment.residual_impact
    return assessment.likelihood, assessment.impact
