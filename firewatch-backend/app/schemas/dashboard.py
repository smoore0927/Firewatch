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
