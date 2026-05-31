"""Control framework + risk-to-control mapping routes.

RBAC summary:
  GET  /frameworks                          — any authenticated user
  DELETE /frameworks/:id                     — admin
  GET  /frameworks/:id/controls             — any authenticated user
  GET  /risks/:id/controls                  — any authenticated user (scope in service)
  POST /risks/:id/controls                  — same RBAC as POST /risks/:id/responses
  DELETE /risks/:id/controls/:mapping_id    — same RBAC as deleting a response
"""

from typing import Annotated, Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db, require_role
from app.core.uploads import read_upload_capped
from app.models.user import User, UserRole
from app.schemas.control import (
    ControlFrameworkResponse,
    ControlResponse,
    FrameworkImportResult,
    FrameworkImportUrlRequest,
    FrameworkUpdate,
    RiskControlCreate,
    RiskControlResponse,
)
from app.core.url_safety import validate_outbound_url
from app.services.audit_service import record_event
from app.services.control_import import detect_and_parse, import_framework
from app.services.control_service import ControlService

router = APIRouter(tags=["Frameworks"])

MAX_IMPORT_BYTES = 25 * 1024 * 1024  # ~25 MB — full OSCAL catalogs are large


@router.get("/frameworks")
def list_frameworks(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ControlFrameworkResponse]:
    return ControlService(db).list_frameworks()


@router.get("/frameworks/{framework_id}/controls")
def list_controls(
    framework_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    q: Annotated[Optional[str], Query()] = None,
) -> list[ControlResponse]:
    controls = ControlService(db).list_controls(framework_id=framework_id, q=q)
    return [ControlResponse.from_control(c) for c in controls]


@router.post("/frameworks/import")
def import_framework_file(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.admin))],
    file: Annotated[UploadFile, File()],
    framework_name: Annotated[Optional[str], Query()] = None,
    version: Annotated[Optional[str], Query()] = None,
) -> FrameworkImportResult:
    """Admin: import a CSV or OSCAL-JSON control catalog from an uploaded file."""
    raw = read_upload_capped(file, MAX_IMPORT_BYTES, detail="Upload exceeds 25 MB limit")
    try:
        parsed = detect_and_parse(raw)
        result = import_framework(db, parsed, framework_name=framework_name, version=version)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    record_event(
        db,
        action="framework.imported",
        user=current_user,
        resource_type="control_framework",
        resource_id=result["framework_name"],
        request=request,
        details={"source": "upload", "created": result["created"], "updated": result["updated"]},
    )
    db.commit()
    return FrameworkImportResult(**result)


async def _fetch_url_bytes(url: str) -> bytes:
    """SSRF-safe fetch: validate + pin resolved IP, no redirects, 25 MB cap."""
    try:
        target = validate_outbound_url(url)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )

    scheme = target.parsed.scheme
    hostname = target.parsed.hostname
    port = target.parsed.port
    hostport = f"{hostname}:{port}" if port is not None else hostname
    path = target.parsed.path or "/"
    query = f"?{target.parsed.query}" if target.parsed.query else ""
    safe_url = f"{scheme}://{hostport}{path}{query}"

    if target.pinned_ip is not None:
        ip = target.pinned_ip
        ip_literal = f"[{ip}]" if ":" in ip else ip
        connect_url = f"{scheme}://{ip_literal}:{target.pinned_port}{path}{query}"
        request_headers = {"Host": hostname}
        extensions = {"sni_hostname": hostname}
    else:
        connect_url = safe_url
        request_headers = {}
        extensions = {}

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as http:
            resp = await http.get(
                connect_url, headers=request_headers, extensions=extensions
            )
            if 300 <= resp.status_code < 400:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=(
                        f"Fetch failed: unexpected redirect (HTTP {resp.status_code}); "
                        "redirects are not followed"
                    ),
                )
            resp.raise_for_status()
            raw = resp.content
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Fetch failed: upstream returned {exc.response.status_code}",
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Fetch failed: {exc}",
        )

    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Fetched file exceeds 25 MB limit",
        )
    return raw


@router.post("/frameworks/import-from-url")
async def import_framework_from_url(
    request: Request,
    body: FrameworkImportUrlRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.admin))],
) -> FrameworkImportResult:
    """Admin: fetch a CSV or OSCAL-JSON control catalog from a URL and import it."""
    raw = await _fetch_url_bytes(body.url)
    try:
        parsed = detect_and_parse(raw)
        result = import_framework(
            db,
            parsed,
            framework_name=body.framework_name,
            version=body.version,
            source_url=body.url,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    record_event(
        db,
        action="framework.imported",
        user=current_user,
        resource_type="control_framework",
        resource_id=result["framework_name"],
        request=request,
        details={"source": "url", "url": body.url, "created": result["created"], "updated": result["updated"]},
    )
    db.commit()
    return FrameworkImportResult(**result)


@router.delete("/frameworks/{framework_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_framework(
    request: Request,
    framework_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.admin))],
) -> None:
    """Admin: delete a framework (blocked when its controls are mapped to risks)."""
    name = ControlService(db).delete_framework(framework_id=framework_id, deleted_by=current_user)
    record_event(
        db,
        action="framework.deleted",
        user=current_user,
        resource_type="control_framework",
        resource_id=name,
        request=request,
        details={"framework_id": framework_id, "name": name},
    )
    db.commit()


@router.patch("/frameworks/{framework_id}")
def update_framework(
    request: Request,
    framework_id: int,
    body: FrameworkUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.admin))],
) -> ControlFrameworkResponse:
    """Admin: edit framework metadata only (never touches controls)."""
    framework = ControlService(db).update_framework(
        framework_id=framework_id,
        name=body.name,
        version=body.version,
        description=body.description,
    )
    record_event(
        db,
        action="framework.updated",
        user=current_user,
        resource_type="control_framework",
        resource_id=framework.name,
        request=request,
        details=body.model_dump(exclude_unset=True),
    )
    db.commit()
    return framework


@router.post("/frameworks/{framework_id}/reimport")
def reimport_framework_file(
    request: Request,
    framework_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.admin))],
    file: Annotated[UploadFile, File()],
    version: Annotated[Optional[str], Query()] = None,
) -> FrameworkImportResult:
    """Admin: replace a framework's controls from an uploaded file (blocked when mapped)."""
    raw = read_upload_capped(file, MAX_IMPORT_BYTES, detail="Upload exceeds 25 MB limit")
    try:
        parsed = detect_and_parse(raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    result = ControlService(db).replace_framework_controls(parsed, framework_id, version=version)
    record_event(
        db,
        action="framework.reimported",
        user=current_user,
        resource_type="control_framework",
        resource_id=result["framework_name"],
        request=request,
        details={"source": "upload", "created": result["created"], "updated": result["updated"]},
    )
    db.commit()
    return FrameworkImportResult(**result)


@router.post("/frameworks/{framework_id}/reimport-from-url")
async def reimport_framework_from_url(
    request: Request,
    framework_id: int,
    body: FrameworkImportUrlRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.admin))],
) -> FrameworkImportResult:
    """Admin: replace a framework's controls from a URL (blocked when mapped)."""
    raw = await _fetch_url_bytes(body.url)
    try:
        parsed = detect_and_parse(raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    result = ControlService(db).replace_framework_controls(
        parsed, framework_id, version=body.version, source_url=body.url
    )
    record_event(
        db,
        action="framework.reimported",
        user=current_user,
        resource_type="control_framework",
        resource_id=result["framework_name"],
        request=request,
        details={"source": "url", "url": body.url, "created": result["created"], "updated": result["updated"]},
    )
    db.commit()
    return FrameworkImportResult(**result)


@router.get("/risks/{risk_id}/controls")
def list_risk_controls(
    risk_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[RiskControlResponse]:
    mappings = ControlService(db).list_risk_controls(risk_id=risk_id, current_user=current_user)
    return [RiskControlResponse.from_mapping(m) for m in mappings]


@router.post("/risks/{risk_id}/controls", status_code=status.HTTP_201_CREATED)
def add_risk_control(
    request: Request,
    risk_id: str,
    data: RiskControlCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RiskControlResponse:
    mapping = ControlService(db).add_mapping(risk_id=risk_id, data=data, created_by=current_user)
    record_event(
        db,
        action="risk.control.mapped",
        user=current_user,
        resource_type="risk",
        resource_id=risk_id,
        request=request,
        details={"control_id": data.control_id, "mapping_type": data.mapping_type},
    )
    db.commit()
    return RiskControlResponse.from_mapping(mapping)


@router.delete("/risks/{risk_id}/controls/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_risk_control(
    request: Request,
    risk_id: str,
    mapping_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    ControlService(db).delete_mapping(risk_id=risk_id, mapping_id=mapping_id, deleted_by=current_user)
    record_event(
        db,
        action="risk.control.unmapped",
        user=current_user,
        resource_type="risk",
        resource_id=risk_id,
        request=request,
        details={"mapping_id": mapping_id},
    )
    db.commit()
