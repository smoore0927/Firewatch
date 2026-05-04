"""
RiskService — all business logic for risks lives here, not in the routes.

Why a service layer?
  Routes should be thin: validate input, call the service, return a response.
  If your business logic lives in routes, it's hard to test (you need an HTTP
  client to call it) and easy to duplicate (two routes that need the same logic
  copy-paste it). The service is a plain class you can instantiate and call
  directly in tests.

Pattern:
  route handler → RiskService method → database → return ORM object
  FastAPI's response_model then serialises the ORM object via Pydantic.
"""

import enum
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.risk import Risk, RiskAssessment, RiskHistory, RiskStatus
from app.models.user import User, UserRole
from app.schemas.risk import AssessmentCreate, RiskCreate, RiskUpdate, TreatmentCreate
from app.models.risk import RiskTreatment


def _to_str(value: object) -> str | None:
    """
    Convert a value to the string we store in risk_history.
    Enum types (like RiskStatus) must use .value — str(RiskStatus.open)
    gives 'RiskStatus.open', not 'open', which the frontend can't use.
    """
    if value is None:
        return None
    if isinstance(value, enum.Enum):
        return value.value
    return str(value)


class RiskService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _generate_risk_id(self) -> str:
        """
        Generate the next RISK-NNN identifier.
        Queries the highest existing numeric suffix and increments it.
        Not collision-safe under extreme concurrency, but fine for typical
        risk register usage. A database sequence would be the production alternative.
        """
        last = (
            self.db.query(Risk)
            .order_by(Risk.id.desc())
            .first()
        )
        if not last:
            return "RISK-001"
        try:
            num = int(last.risk_id.split("-")[1]) + 1
        except (IndexError, ValueError):
            # Fallback if risk_id format is unexpected
            num = self.db.query(Risk).count() + 1
        return f"RISK-{num:03d}"

    def _get_active_risk(self, risk_id: str) -> Risk:
        """Fetch a non-deleted risk by its human-readable ID, or raise 404."""
        risk = (
            self.db.query(Risk)
            .filter(Risk.risk_id == risk_id, Risk.deleted_at.is_(None))
            .first()
        )
        if not risk:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Risk '{risk_id}' not found",
            )
        return risk

    def _check_edit_permission(self, risk: Risk, user: User) -> None:
        """
        Enforce edit rules by role:
          - executive_viewer  → never allowed to edit
          - risk_owner        → only their own risks
          - security_analyst  → any risk
          - admin             → any risk
        """
        if user.role == UserRole.executive_viewer:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Executive viewers have read-only access",
            )
        if user.role == UserRole.risk_owner and risk.owner_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Risk owners can only edit risks assigned to them",
            )

    # -----------------------------------------------------------------------
    # Read
    # -----------------------------------------------------------------------

    def list_risks(
        self,
        current_user: User,
        status_filter: RiskStatus | None = None,
        category: str | None = None,
        owner_id: int | None = None,
        due_for_review: bool | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> dict:
        query = self.db.query(Risk).filter(Risk.deleted_at.is_(None))

        # Role-based data scoping: risk_owners only see their assigned risks
        if current_user.role == UserRole.risk_owner:
            query = query.filter(Risk.owner_id == current_user.id)

        if status_filter:
            query = query.filter(Risk.status == status_filter)
        if category:
            query = query.filter(Risk.category == category)
        if owner_id:
            query = query.filter(Risk.owner_id == owner_id)
        if due_for_review:
            query = query.filter(Risk.next_review_date.isnot(None))
            query = query.filter(Risk.next_review_date <= date.today())
            query = query.filter(Risk.status.notin_([RiskStatus.closed, RiskStatus.mitigated]))

        total = query.count()
        items = (
            query.order_by(Risk.created_at.desc())
            .options(
                joinedload(Risk.owner),
                selectinload(Risk.assessments),
                selectinload(Risk.treatments),
                selectinload(Risk.history),
            )
            .offset(skip)
            .limit(limit)
            .all()
        )
        return {"total": total, "items": items}

    def get_risk(self, risk_id: str) -> Risk:
        return self._get_active_risk(risk_id)

    # -----------------------------------------------------------------------
    # Create
    # -----------------------------------------------------------------------

    def create_risk(self, risk_data: RiskCreate, created_by: User) -> Risk:
        risk = Risk(
            risk_id=self._generate_risk_id(),
            title=risk_data.title,
            description=risk_data.description,
            threat_source=risk_data.threat_source,
            threat_event=risk_data.threat_event,
            vulnerability=risk_data.vulnerability,
            affected_asset=risk_data.affected_asset,
            category=risk_data.category,
            owner_id=risk_data.owner_id if risk_data.owner_id else created_by.id,
            created_by_id=created_by.id,
            status=RiskStatus.open,
            review_frequency_days=risk_data.review_frequency_days,
            next_review_date=risk_data.next_review_date,
        )
        self.db.add(risk)
        # flush writes the INSERT so risk.id is populated, but doesn't commit yet —
        # the whole operation (risk + assessment) commits together or not at all
        self.db.flush()

        if risk_data.likelihood is not None and risk_data.impact is not None:
            assessment = RiskAssessment(
                risk_id=risk.id,
                likelihood=risk_data.likelihood,
                impact=risk_data.impact,
                risk_score=risk_data.likelihood * risk_data.impact,
                assessed_by_id=created_by.id,
            )
            self.db.add(assessment)

        self.db.commit()
        self.db.refresh(risk)
        return risk

    # -----------------------------------------------------------------------
    # Update
    # -----------------------------------------------------------------------

    def update_risk(self, risk_id: str, risk_data: RiskUpdate, updated_by: User) -> Risk:
        risk = self._get_active_risk(risk_id)
        self._check_edit_permission(risk, updated_by)

        # exclude_unset=True means fields the caller didn't send are not in this dict,
        # so we don't accidentally overwrite data with None
        update_fields = risk_data.model_dump(exclude_unset=True)

        # Pull out scoring fields before iterating — they need special handling
        new_likelihood = update_fields.pop("likelihood", None)
        new_impact = update_fields.pop("impact", None)

        # Write a history row for every field that actually changed.
        # _to_str() handles enum values correctly (stores "open" not "RiskStatus.open").
        for field, new_value in update_fields.items():
            old_value = getattr(risk, field, None)
            if old_value != new_value:
                self.db.add(RiskHistory(
                    risk_id=risk.id,
                    field_changed=field,
                    old_value=_to_str(old_value),
                    new_value=_to_str(new_value),
                    changed_by_id=updated_by.id,
                ))
                setattr(risk, field, new_value)

        # If either scoring value was sent, create a new assessment row
        if new_likelihood is not None or new_impact is not None:
            latest = risk.assessments[0] if risk.assessments else None
            lh = new_likelihood if new_likelihood is not None else (latest.likelihood if latest else 1)
            im = new_impact if new_impact is not None else (latest.impact if latest else 1)
            self.db.add(RiskAssessment(
                risk_id=risk.id,
                likelihood=lh,
                impact=im,
                risk_score=lh * im,
                assessed_by_id=updated_by.id,
            ))
            if risk.review_frequency_days:
                risk.next_review_date = date.today() + timedelta(days=risk.review_frequency_days)

        self.db.commit()
        self.db.refresh(risk)
        return risk

    # -----------------------------------------------------------------------
    # Assessment (standalone — add a new scoring to an existing risk)
    # -----------------------------------------------------------------------

    def add_assessment(
        self, risk_id: str, data: AssessmentCreate, assessed_by: User
    ) -> Risk:
        risk = self._get_active_risk(risk_id)
        self._check_edit_permission(risk, assessed_by)

        residual_score = None
        if data.residual_likelihood is not None and data.residual_impact is not None:
            residual_score = data.residual_likelihood * data.residual_impact

        self.db.add(RiskAssessment(
            risk_id=risk.id,
            likelihood=data.likelihood,
            impact=data.impact,
            risk_score=data.likelihood * data.impact,
            residual_likelihood=data.residual_likelihood,
            residual_impact=data.residual_impact,
            residual_risk_score=residual_score,
            notes=data.notes,
            assessed_by_id=assessed_by.id,
        ))
        if risk.review_frequency_days:
            risk.next_review_date = date.today() + timedelta(days=risk.review_frequency_days)
        self.db.commit()
        self.db.refresh(risk)
        return risk

    # -----------------------------------------------------------------------
    # Treatment
    # -----------------------------------------------------------------------

    def add_treatment(
        self, risk_id: str, data: TreatmentCreate, created_by: User
    ) -> Risk:
        risk = self._get_active_risk(risk_id)
        self._check_edit_permission(risk, created_by)

        self.db.add(RiskTreatment(
            risk_id=risk.id,
            treatment_type=data.treatment_type,
            mitigation_strategy=data.mitigation_strategy,
            owner_id=data.owner_id if data.owner_id else created_by.id,
            start_date=data.start_date,
            target_date=data.target_date,
            cost_estimate=data.cost_estimate,
            notes=data.notes,
        ))
        self.db.commit()
        self.db.refresh(risk)
        return risk

    # -----------------------------------------------------------------------
    # Delete (soft)
    # -----------------------------------------------------------------------

    def delete_risk(self, risk_id: str) -> None:
        """
        Soft delete: set deleted_at instead of issuing DELETE.
        The risk and all its history remain in the database for audit purposes.
        """
        risk = self._get_active_risk(risk_id)
        risk.deleted_at = datetime.now(timezone.utc)
        self.db.commit()
