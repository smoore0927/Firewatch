"""Outbound webhook subscription management (admin only).

Subscriptions are configured here; events are emitted by the rest of the app
(see app/services/events.py and app/services/webhook_service.py).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, require_role
from app.core.url_safety import validate_outbound_url
from app.models.user import User, UserRole
from app.schemas.webhook import (
    WebhookDeliveryListResponse,
    WebhookSubscriptionCreate,
    WebhookSubscriptionCreatedResponse,
    WebhookSubscriptionResponse,
    WebhookSubscriptionUpdate,
)
from app.services import webhook_service
from app.services.audit_service import record_event

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def _validate_url_or_422(url: str) -> None:
    try:
        validate_outbound_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.get("", response_model=list[WebhookSubscriptionResponse])
def list_subscriptions(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_role(UserRole.admin))],
):
    return webhook_service.list_all(db)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=WebhookSubscriptionCreatedResponse)
def create_subscription(
    request: Request,
    body: WebhookSubscriptionCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.admin))],
):
    target_url = str(body.target_url)
    _validate_url_or_422(target_url)
    row, plaintext = webhook_service.create(
        db,
        name=body.name,
        target_url=target_url,
        event_types=list(body.event_types),
        created_by=current_user.id,
    )
    record_event(
        db,
        action="webhook.created",
        user=current_user,
        resource_type="webhook",
        resource_id=str(row.id),
        request=request,
        details={
            "name": row.name,
            "target_url": row.target_url,
            "event_types": row.event_types,
        },
    )
    db.commit()
    return WebhookSubscriptionCreatedResponse(
        id=row.id,
        name=row.name,
        target_url=row.target_url,
        event_types=row.event_types,
        is_active=row.is_active,
        created_at=row.created_at,
        last_delivered_at=row.last_delivered_at,
        consecutive_failures=row.consecutive_failures,
        created_by_id=row.created_by_id,
        secret=plaintext,
    )


@router.get("/{sub_id}", response_model=WebhookSubscriptionResponse)
def get_subscription(
    sub_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_role(UserRole.admin))],
):
    return webhook_service.get(db, sub_id)


@router.patch("/{sub_id}", response_model=WebhookSubscriptionResponse)
def update_subscription(
    request: Request,
    sub_id: int,
    body: WebhookSubscriptionUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.admin))],
):
    sub = webhook_service.get(db, sub_id)
    new_target_url = str(body.target_url) if body.target_url is not None else None
    if new_target_url is not None:
        _validate_url_or_422(new_target_url)
    updated = webhook_service.update(
        db,
        sub,
        name=body.name,
        target_url=new_target_url,
        event_types=list(body.event_types) if body.event_types is not None else None,
        is_active=body.is_active,
    )
    record_event(
        db,
        action="webhook.updated",
        user=current_user,
        resource_type="webhook",
        resource_id=str(updated.id),
        request=request,
        details=body.model_dump(exclude_unset=True, mode="json"),
    )
    db.commit()
    return updated


@router.delete("/{sub_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subscription(
    request: Request,
    sub_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.admin))],
) -> None:
    sub = webhook_service.get(db, sub_id)
    details = {"name": sub.name, "target_url": sub.target_url}
    webhook_service.delete(db, sub)
    record_event(
        db,
        action="webhook.deleted",
        user=current_user,
        resource_type="webhook",
        resource_id=str(sub_id),
        request=request,
        details=details,
    )
    db.commit()


@router.post("/{sub_id}/test", status_code=status.HTTP_202_ACCEPTED)
async def fire_test(
    sub_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_role(UserRole.admin))],
) -> dict:
    """Fire a synthetic firewatch.test event at this subscription only."""
    sub = webhook_service.get(db, sub_id)
    _validate_url_or_422(sub.target_url)
    delivery_id = await webhook_service.fire_test_event(db, sub)
    return {"delivery_id": delivery_id}


@router.get("/{sub_id}/deliveries", response_model=WebhookDeliveryListResponse)
def list_deliveries(
    sub_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_role(UserRole.admin))],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    result = webhook_service.list_deliveries(db, sub_id, skip=skip, limit=limit)
    return WebhookDeliveryListResponse(**result)
