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
  POST /risks/:id/treatments      — any authenticated user (service checks ownership)
  DELETE /risks/:id               — admin only
  GET  /risks/export              — any authenticated user (CSV download)
  GET  /risks/import-template     — any authenticated user (CSV download)
  POST /risks/import              — admin, security_analyst (CSV upload)
"""

from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db, require_role
from app.models.risk import RiskStatus
from app.models.user import User, UserRole
from app.schemas.risk import (
    AssessmentCreate,
    ImportResult,
    ImportResultRow,
    RiskCreate,
    RiskListResponse,
    RiskResponse,
    RiskUpdate,
    TreatmentCreate,
)
from app.services.csv_service import (
    import_template_csv,
    parse_risks_csv,
    risks_to_csv,
)
from app.services.risk_service import RiskService

router = APIRouter(prefix="/risks", tags=["Risks"])

MAX_IMPORT_BYTES = 5 * 1024 * 1024  # ~5 MB


@router.get("")
def list_risks(
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
    risk_data: RiskCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.admin, UserRole.security_analyst, UserRole.risk_owner))],
) -> RiskResponse:
    return RiskService(db).create_risk(risk_data=risk_data, created_by=current_user)


# ---------------------------------------------------------------------------
# CSV export / import — must be declared BEFORE /{risk_id} so the literal
# path segments aren't captured as risk_id="export" etc.
# ---------------------------------------------------------------------------

@router.get("/export")
def export_risks(
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
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.admin, UserRole.security_analyst))],
) -> ImportResult:
    """Bulk-create risks from an uploaded CSV. Errors are reported per row."""
    raw = file.file.read()
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="CSV upload exceeds 5 MB limit",
        )

    content = raw.decode("utf-8-sig", errors="replace")
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

    return ImportResult(created=created, errors=errors)


# ---------------------------------------------------------------------------
# Path-param routes — keep below all literal-path routes
# ---------------------------------------------------------------------------

@router.get("/{risk_id}")
def get_risk(
    risk_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> RiskResponse:
    return RiskService(db).get_risk(risk_id=risk_id)


@router.put("/{risk_id}")
def update_risk(
    risk_id: str,
    risk_data: RiskUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RiskResponse:
    return RiskService(db).update_risk(
        risk_id=risk_id, risk_data=risk_data, updated_by=current_user
    )


@router.post("/{risk_id}/assessments")
def add_assessment(
    risk_id: str,
    data: AssessmentCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RiskResponse:
    """Add a new scoring assessment to an existing risk."""
    return RiskService(db).add_assessment(
        risk_id=risk_id, data=data, assessed_by=current_user
    )


@router.post("/{risk_id}/treatments")
def add_treatment(
    risk_id: str,
    data: TreatmentCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RiskResponse:
    """Add a mitigation/treatment plan to a risk."""
    return RiskService(db).add_treatment(
        risk_id=risk_id, data=data, created_by=current_user
    )


@router.delete("/{risk_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_risk(
    risk_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_role(UserRole.admin))],
) -> None:
    """Soft-delete a risk. Admin only. The record is retained for audit purposes."""
    RiskService(db).delete_risk(risk_id=risk_id)
