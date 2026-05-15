from __future__ import annotations

from pydantic import BaseModel


class VelocityMTTMBySeverity(BaseModel):
    critical: float | None
    high: float | None
    medium: float | None
    low: float | None


class VelocityMTTMResponse(BaseModel):
    mean_days: float | None
    median_days: float | None
    count: int
    by_severity: VelocityMTTMBySeverity


class VelocityThroughputPoint(BaseModel):
    period: str   # YYYY-MM
    opened: int
    closed: int


class VelocityThroughputResponse(BaseModel):
    points: list[VelocityThroughputPoint]


class ResidualReductionBySeverity(BaseModel):
    critical: float | None
    high: float | None
    medium: float | None
    low: float | None


class ResidualReductionResponse(BaseModel):
    avg_absolute: float | None
    avg_percentage: float | None
    count: int
    by_severity: ResidualReductionBySeverity
