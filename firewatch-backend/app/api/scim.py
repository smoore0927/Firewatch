"""SCIM 2.0 provisioning endpoints (RFC 7644)."""

from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, require_scim_token
from app.models.user import User
from app.schemas.scim import (
    SCIMError,
    SCIMListResponse,
    SCIMPatchRequest,
    SCIMUser,
)
from app.services.audit_service import record_event
from app.services.scim_service import (
    SCIMConflictError,
    SCIMInvalidFilterError,
    SCIMNotFoundError,
    apply_patch_ops,
    create_user_from_scim,
    parse_scim_filter,
    replace_user_from_scim,
    user_to_scim,
)

router = APIRouter(
    prefix="/scim/v2",
    tags=["SCIM"],
    dependencies=[Depends(require_scim_token)],
)


def _scim_error_response(
    status_code: int, detail: str | None = None, scim_type: str | None = None
) -> JSONResponse:
    """Render an HTTPException-style failure as a SCIM Error resource."""
    body = SCIMError(status=str(status_code), detail=detail, scimType=scim_type)
    return JSONResponse(status_code=status_code, content=body.model_dump(exclude_none=True))


def _base_url(request: Request) -> str:
    """Best-effort base URL for meta.location (drops any path component)."""
    return str(request.base_url).rstrip("/")


def _scim_response(payload: SCIMUser, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(exclude_none=True, mode="json"),
    )


# --- Discovery endpoints --------------------------------------------------------


@router.get("/ServiceProviderConfig")
def service_provider_config() -> dict[str, Any]:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "patch": {"supported": True},
        "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": 200},
        "changePassword": {"supported": False},
        "sort": {"supported": False},
        "etag": {"supported": False},
        "authenticationSchemes": [
            {"name": "OAuth Bearer Token", "type": "oauthbearertoken", "primary": True}
        ],
    }


@router.get("/ResourceTypes")
def resource_types() -> list[dict[str, Any]]:
    return [
        {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"],
            "id": "User",
            "name": "User",
            "endpoint": "/Users",
            "description": "User Account",
            "schema": "urn:ietf:params:scim:schemas:core:2.0:User",
        }
    ]


@router.get("/Schemas")
def schemas_endpoint() -> list[dict[str, Any]]:
    return [
        {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Schema"],
            "id": "urn:ietf:params:scim:schemas:core:2.0:User",
            "name": "User",
            "description": "Firewatch User",
        }
    ]


# --- /Users ---------------------------------------------------------------------


@router.get("/Users")
def list_users(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    filter: Annotated[str | None, Query(alias="filter")] = None,
    startIndex: Annotated[int, Query(ge=1)] = 1,
    count: Annotated[int, Query(ge=0, le=200)] = 100,
):
    try:
        parsed = parse_scim_filter(filter)
    except SCIMInvalidFilterError as exc:
        return _scim_error_response(400, str(exc), scim_type="invalidFilter")

    query = db.query(User)
    if parsed:
        if parsed["attr"] == "userName":
            query = query.filter(User.email == parsed["value"])
        elif parsed["attr"] == "externalId":
            query = query.filter(User.external_id == parsed["value"])

    total = query.count()
    rows = query.order_by(User.id).offset(startIndex - 1).limit(count).all()
    base = _base_url(request)
    resources = [user_to_scim(u, base) for u in rows]
    body = SCIMListResponse(
        totalResults=total,
        startIndex=startIndex,
        itemsPerPage=len(resources),
        Resources=resources,
    )
    return JSONResponse(
        status_code=200,
        content=body.model_dump(exclude_none=True, mode="json"),
    )


@router.get("/Users/{user_id}")
def get_user(
    request: Request,
    user_id: int,
    db: Annotated[Session, Depends(get_db)],
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return _scim_error_response(404, f"User {user_id} not found")
    return _scim_response(user_to_scim(user, _base_url(request)))


@router.post("/Users", status_code=201)
def create_user(
    request: Request,
    payload: SCIMUser,
    db: Annotated[Session, Depends(get_db)],
):
    try:
        user = create_user_from_scim(db, payload)
    except SCIMConflictError as exc:
        return _scim_error_response(409, str(exc), scim_type="uniqueness")

    record_event(
        db,
        action="scim.user.created",
        user=user,
        resource_type="user",
        resource_id=str(user.id),
        request=request,
        details={"email": user.email},
    )
    db.commit()
    return _scim_response(user_to_scim(user, _base_url(request)), status_code=201)


@router.put("/Users/{user_id}")
def replace_user(
    request: Request,
    user_id: int,
    payload: SCIMUser,
    db: Annotated[Session, Depends(get_db)],
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return _scim_error_response(404, f"User {user_id} not found")

    user = replace_user_from_scim(db, user, payload)
    record_event(
        db,
        action="scim.user.replaced",
        user=user,
        resource_type="user",
        resource_id=str(user.id),
        request=request,
        details={"active": user.is_active},
    )
    db.commit()
    return _scim_response(user_to_scim(user, _base_url(request)))


@router.patch("/Users/{user_id}")
def patch_user(
    request: Request,
    user_id: int,
    payload: SCIMPatchRequest,
    db: Annotated[Session, Depends(get_db)],
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return _scim_error_response(404, f"User {user_id} not found")

    previous_active = user.is_active
    user = apply_patch_ops(db, user, payload.Operations)

    details: dict[str, Any] = {}
    if previous_active != user.is_active:
        details["active"] = user.is_active
    record_event(
        db,
        action="scim.user.patched",
        user=user,
        resource_type="user",
        resource_id=str(user.id),
        request=request,
        details=details or None,
    )
    db.commit()
    return _scim_response(user_to_scim(user, _base_url(request)))


@router.delete("/Users/{user_id}", status_code=204)
def delete_user(
    request: Request,
    user_id: int,
    db: Annotated[Session, Depends(get_db)],
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return _scim_error_response(404, f"User {user_id} not found")

    user.is_active = False
    user.last_logout_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    record_event(
        db,
        action="scim.user.deleted",
        user=user,
        resource_type="user",
        resource_id=str(user.id),
        request=request,
        details={"email": user.email},
    )
    db.commit()
    return Response(status_code=204)
