from __future__ import annotations

from pydantic import BaseModel


class DashboardSummaryResponse(BaseModel):
    total: int
    by_status: dict[str, int]
    by_severity: dict[str, int]
    overdue_treatments: int
    overdue_reviews: int
    risk_matrix: list[list[int]]


class ScoreHistoryPoint(BaseModel):
    date: str        # YYYY-MM-DD
    avg_score: float
    count: int       # number of assessments on that date


class ScoreHistoryResponse(BaseModel):
    points: list[ScoreHistoryPoint]


class ScoreTotalsBySeverityPoint(BaseModel):
    date: str         # YYYY-MM-DD
    low: int          # sum of risk_score for assessments where score <= 5
    medium: int       # sum where 5 < score <= 12
    high: int         # sum where 12 < score <= 20
    critical: int     # sum where score > 20


class ScoreTotalsBySeverityResponse(BaseModel):
    points: list[ScoreTotalsBySeverityPoint]
