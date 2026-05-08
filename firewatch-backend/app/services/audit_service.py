"""Audit logging helper — records security-relevant events."""

import json
import logging

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User

logger = logging.getLogger(__name__)


def record_event(
    db: Session,
    *,
    action: str,
    user: User | None = None,
    user_email: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    request: Request | None = None,
    details: dict | None = None,
) -> None:
    """
    Stage an audit row on the session — does NOT commit.
    Caller commits as part of the surrounding transaction so the audit row
    participates atomically. Defensive: any failure is swallowed and logged.
    """
    try:
        ip_address: str | None = None
        user_agent: str | None = None
        if request is not None:
            if request.client is not None:
                ip_address = request.client.host
            user_agent = request.headers.get("user-agent")

        resolved_email = user_email
        if resolved_email is None and user is not None:
            resolved_email = user.email

        encoded_details = json.dumps(details) if details is not None else None

        db.add(AuditLog(
            user_id=user.id if user is not None else None,
            user_email=resolved_email,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent[:500] if user_agent else None,
            details=encoded_details,
        ))
    except Exception:
        logger.exception("Failed to record audit event %s", action)
