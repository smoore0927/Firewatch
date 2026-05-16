"""Pydantic schemas for the consolidated risk report endpoint."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.core.roles import UserRole
from app.schemas.dashboard import DashboardSummaryResponse, ScoreHistoryResponse


class ReportUserRef(BaseModel):
    id: int
    email: str
    full_name: str | None
    role: UserRole


class ReportDateRange(BaseModel):
    start: date
    end: date


class RiskReportRow(BaseModel):
    id: int
    title: str
    category: str | None
    status: str
    current_likelihood: int | None
    current_impact: int | None
    current_score: int | None
    severity: Literal["Low", "Medium", "High", "Critical", "Unscored"]
    owner_name: str | None
    next_review_date: date | None


class RiskReportResponse(BaseModel):
    generated_at: datetime
    generated_by: ReportUserRef
    date_range: ReportDateRange
    summary: DashboardSummaryResponse
    score_history: ScoreHistoryResponse
    risks: list[RiskReportRow] | None
