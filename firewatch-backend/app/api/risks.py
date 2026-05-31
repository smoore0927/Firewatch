"""
Risk CRUD routes.

Route → Service pattern:
  Routes are deliberately thin here — they validate input (Pydantic does this
  automatically), call the service, and return a response. Business rules and
  database logic live in RiskService, which makes them testable independently.

RBAC summary:
  GET  /risks, GET /risks/:id     — any authenticated user (scope enforced in service)
  POST /risks                     — admin, security_analyst, risk_owner
  PUT  /risks/:id                 — any authenticated user (service checks ownership)
  POST /risks/:id/assessments     — any authenticated user (service checks ownership)
  POST /risks/:id/responses       — any authenticated user (service checks ownership)
  DELETE /risks/:id               — admin only
  GET  /risks/export              — any authenticated user (CSV download)
  GET  /risks/import-template     — any authenticated user (CSV download)
  POST /risks/import              — admin, security_analyst (CSV upload)
"""

from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db, require_role
from app.core.uploads import read_upload_capped
from app.models.risk import RiskStatus
from app.models.user import User, UserRole
from app.schemas.risk import (
    AssessmentCreate,
    BulkRescoreRequest,
    BulkReassignRequest,
    BulkRiskError,
    BulkRiskResult,
    BulkStatusRequest,
    ImportResult,
    ImportResultRow,
    ResponseCreate,
    ResponseUpdate,
    RiskCreate,
    RiskListResponse,
    RiskResponse,
    RiskUpdate,
)
from app.services.audit_service import record_event
from app.services.csv_service import (
    import_template_csv,
    parse_risks_csv,
    risks_to_csv,
    validate_import_headers,
)
from app.services.risk_service import RiskService

router = APIRouter(prefix="/risks", tags=["Risks"])

MAX_IMPORT_BYTES = 5 * 1024 * 1024  # ~5 MB


@router.get("")
def list_risks(
    *,
    status_filter: Annotated[Optional[RiskStatus], Query(alias="status")] = None,
    category: Annotated[Optional[str], Query()] = None,
    owner_id: Annotated[Optional[int], Query()] = None,
    due_for_review: Annotated[Optional[bool], Query()] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RiskListResponse:
    service = RiskService(db)
    result = service.list_risks(
        current_user=current_user,
        status_filter=status_filter,
        category=category,
        owner_id=owner_id,
        due_for_review=due_for_review,
        skip=skip,
        limit=limit,
    )
    return RiskListResponse(**result)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_risk(
    request: Request,
    risk_data: RiskCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.admin, UserRole.security_analyst, UserRole.risk_owner))],
) -> RiskResponse:
    risk = RiskService(db).create_risk(risk_data=risk_data, created_by=current_user)
    record_event(
        db,
        action="risk.created",
        user=current_user,
        resource_type="risk",
        resource_id=risk.risk_id,
        request=request,
    )
    db.commit()
    return risk


# ---------------------------------------------------------------------------
# CSV export / import — must be declared BEFORE /{risk_id} so the literal
# path segments aren't captured as risk_id="export" etc.
# ---------------------------------------------------------------------------

@router.get("/export")
def export_risks(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Response:
    """Download all risks visible to the current user as a CSV file."""
    result = RiskService(db).list_risks(
        current_user=current_user,
        skip=0,
        limit=10000,
    )
    csv_text = risks_to_csv(result["items"])
    filename = f"firewatch-risks-{date.today().isoformat()}.csv"
    record_event(
        db,
        action="risk.exported",
        user=current_user,
        resource_type="risk",
        request=request,
        details={"count": len(result["items"])},
    )
    db.commit()
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/import-template")
def import_template(
    _: Annotated[User, Depends(get_current_user)],
) -> Response:
    """Download a CSV template (header + one example row) for risk import."""
    csv_text = import_template_csv()
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="firewatch-import-template.csv"'
        },
    )


@router.post("/import")
def import_risks(
    request: Request,
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.admin, UserRole.security_analyst))],
) -> ImportResult:
    """Bulk-create risks from an uploaded CSV. Errors are reported per row."""
    raw = read_upload_capped(file, MAX_IMPORT_BYTES, detail="CSV upload exceeds 5 MB limit")

    content = raw.decode("utf-8-sig", errors="replace")
    try:
        validate_import_headers(content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    parsed = parse_risks_csv(content)

    service = RiskService(db)
    created = 0
    errors: list[ImportResultRow] = []

    for row_number, risk_create, owner_email, error in parsed:
        if error or risk_create is None:
            errors.append(ImportResultRow(row=row_number, message=error or "invalid row"))
            continue

        try:
            if owner_email:
                owner = (
                    db.query(User)
                    .filter(User.email == owner_email, User.is_active.is_(True))
                    .first()
                )
                if not owner:
                    errors.append(ImportResultRow(
                        row=row_number,
                        message=f"owner_email '{owner_email}' does not match an active user",
                    ))
                    continue
                risk_create.owner_id = owner.id

            service.create_risk(risk_data=risk_create, created_by=current_user)
            created += 1
        except Exception as exc:
            db.rollback()
            errors.append(ImportResultRow(row=row_number, message=f"create failed: {exc}"))

    result = ImportResult(created=created, errors=errors)
    record_event(
        db,
        action="risk.imported",
        user=current_user,
        resource_type="risk",
        request=request,
        details={"created": result.created, "errors": len(result.errors)},
    )
    db.commit()
    return result


# ---------------------------------------------------------------------------
# Bulk action routes — literal paths, must come before /{risk_id}
# ---------------------------------------------------------------------------


def _to_bulk_result(raw: dict) -> BulkRiskResult:
    return BulkRiskResult(
        updated=raw["updated"],
        errors=[BulkRiskError(**e) for e in raw["errors"]],
    )


@router.post("/bulk/reassign")
def bulk_reassign(
    request: Request,
    payload: BulkReassignRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.admin, UserRole.security_analyst))],
) -> BulkRiskResult:
    """Reassign owner_id on multiple risks. Admin/analyst only."""
    service = RiskService(db)
    update = RiskUpdate(owner_id=payload.owner_id)
    raw = service.bulk_apply(
        payload.risk_ids,
        lambda rid: service.update_risk(risk_id=rid, risk_data=update, updated_by=current_user),
    )
    record_event(
        db,
        action="risk.bulk_reassigned",
        user=current_user,
        resource_type="risk",
        request=request,
        details={
            "updated": len(raw["updated"]),
            "errors": len(raw["errors"]),
            "owner_id": payload.owner_id,
        },
    )
    db.commit()
    return _to_bulk_result(raw)


@router.post("/bulk/status")
def bulk_status(
    request: Request,
    payload: BulkStatusRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BulkRiskResult:
    """Change status on multiple risks. Per-risk ownership enforced by the service."""
    service = RiskService(db)
    update = RiskUpdate(status=payload.status)
    raw = service.bulk_apply(
        payload.risk_ids,
        lambda rid: service.update_risk(risk_id=rid, risk_data=update, updated_by=current_user),
    )
    record_event(
        db,
        action="risk.bulk_status_changed",
        user=current_user,
        resource_type="risk",
        request=request,
        details={
            "updated": len(raw["updated"]),
            "errors": len(raw["errors"]),
            "status": payload.status.value,
        },
    )
    db.commit()
    return _to_bulk_result(raw)


@router.post("/bulk/rescore")
def bulk_rescore(
    request: Request,
    payload: BulkRescoreRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BulkRiskResult:
    """Append a new assessment (likelihood/impact) to multiple risks."""
    service = RiskService(db)
    assessment = AssessmentCreate(
        likelihood=payload.likelihood,
        impact=payload.impact,
        notes=payload.notes,
    )
    raw = service.bulk_apply(
        payload.risk_ids,
        lambda rid: service.add_assessment(risk_id=rid, data=assessment, assessed_by=current_user),
    )
    record_event(
        db,
        action="risk.bulk_rescored",
        user=current_user,
        resource_type="risk",
        request=request,
        details={
            "updated": len(raw["updated"]),
            "errors": len(raw["errors"]),
            "likelihood": payload.likelihood,
            "impact": payload.impact,
        },
    )
    db.commit()
    return _to_bulk_result(raw)


# ---------------------------------------------------------------------------
# Path-param routes — keep below all literal-path routes
# ---------------------------------------------------------------------------

@router.get("/{risk_id}")
def get_risk(
    risk_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RiskResponse:
    return RiskService(db).get_risk(risk_id=risk_id, current_user=current_user)


@router.put("/{risk_id}")
def update_risk(
    request: Request,
    risk_id: str,
    risk_data: RiskUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RiskResponse:
    risk = RiskService(db).update_risk(
        risk_id=risk_id, risk_data=risk_data, updated_by=current_user
    )
    record_event(
        db,
        action="risk.updated",
        user=current_user,
        resource_type="risk",
        resource_id=risk.risk_id,
        request=request,
    )
    db.commit()
    return risk


@router.post("/{risk_id}/assessments")
def add_assessment(
    request: Request,
    risk_id: str,
    data: AssessmentCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RiskResponse:
    """Add a new scoring assessment to an existing risk."""
    risk = RiskService(db).add_assessment(
        risk_id=risk_id, data=data, assessed_by=current_user
    )
    record_event(
        db,
        action="risk.assessment.added",
        user=current_user,
        resource_type="risk",
        resource_id=risk.risk_id,
        request=request,
        details={"likelihood": data.likelihood, "impact": data.impact},
    )
    db.commit()
    return risk


@router.post("/{risk_id}/responses")
def add_response(
    request: Request,
    risk_id: str,
    data: ResponseCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RiskResponse:
    """Add a response/mitigation plan to a risk."""
    risk = RiskService(db).add_response(
        risk_id=risk_id, data=data, created_by=current_user
    )
    record_event(
        db,
        action="risk.response.added",
        user=current_user,
        resource_type="risk",
        resource_id=risk.risk_id,
        request=request,
        details={"response_type": data.response_type.value},
    )
    db.commit()
    return risk


@router.patch("/{risk_id}/responses/{response_id}")
def update_response(
    request: Request,
    risk_id: str,
    response_id: int,
    data: ResponseUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RiskResponse:
    """Update fields on an existing response/mitigation plan."""
    risk = RiskService(db).update_response(
        risk_id=risk_id, response_id=response_id, data=data, updated_by=current_user
    )
    record_event(
        db,
        action="risk.response.updated",
        user=current_user,
        resource_type="risk",
        resource_id=risk.risk_id,
        request=request,
        details={"response_id": response_id, "fields": list(data.model_dump(exclude_unset=True).keys())},
    )
    db.commit()
    return risk


@router.delete("/{risk_id}/responses/{response_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_response(
    request: Request,
    risk_id: str,
    response_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    RiskService(db).delete_response(
        risk_id=risk_id, response_id=response_id, deleted_by=current_user
    )
    record_event(
        db,
        action="risk.response.deleted",
        user=current_user,
        resource_type="risk",
        resource_id=risk_id,
        request=request,
        details={"response_id": response_id},
    )
    db.commit()


@router.delete("/{risk_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_risk(
    request: Request,
    risk_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_admin: Annotated[User, Depends(require_role(UserRole.admin))],
) -> None:
    """Soft-delete a risk. Admin only. The record is retained for audit purposes."""
    RiskService(db).delete_risk(risk_id=risk_id)
    record_event(
        db,
        action="risk.deleted",
        user=current_admin,
        resource_type="risk",
        resource_id=risk_id,
        request=request,
    )
    db.commit()
