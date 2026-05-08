"""Audit log read API — admin only."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, require_role
from app.models.audit_log import AuditLog
from app.models.user import User, UserRole
from app.schemas.audit_log import (
    AuditActionsResponse,
    AuditLogListResponse,
    AuditLogResponse,
)

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("/logs", response_model=AuditLogListResponse)
def list_audit_logs(
    *,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_role(UserRole.admin))],
    action: Annotated[str | None, Query()] = None,
    user_id: Annotated[int | None, Query()] = None,
    resource_type: Annotated[str | None, Query()] = None,
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditLogListResponse:
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)
    if start:
        query = query.filter(AuditLog.created_at >= start)
    if end:
        query = query.filter(AuditLog.created_at <= end)

    total = query.count()
    items = (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return AuditLogListResponse(
        total=total,
        items=[AuditLogResponse.model_validate(item) for item in items],
    )


@router.get("/actions", response_model=AuditActionsResponse)
def list_audit_actions(
    *,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_role(UserRole.admin))],
) -> AuditActionsResponse:
    rows = (
        db.query(AuditLog.action)
        .distinct()
        .order_by(AuditLog.action.asc())
        .all()
    )
    return AuditActionsResponse(actions=[action for (action,) in rows])
