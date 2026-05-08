"""Consolidated report endpoints — feed the frontend PDF exporter."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.report import RiskReportResponse
from app.services.audit_service import record_event
from app.services.report_service import build_risk_report

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/risk-summary", response_model=RiskReportResponse)
def get_risk_summary_report(
    request: Request,
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    include_risks: Annotated[bool, Query()] = False,
) -> RiskReportResponse:
    payload = build_risk_report(
        db=db,
        user=current_user,
        start=start,
        end=end,
        include_risks=include_risks,
    )
    record_event(
        db,
        action="report_exported",
        user=current_user,
        resource_type="report",
        request=request,
        details={
            "start": start.isoformat(),
            "end": end.isoformat(),
            "include_risks": include_risks,
        },
    )
    db.commit()
    return payload
