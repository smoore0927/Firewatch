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
from typing import Callable

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.risk import Risk, RiskAssessment, RiskHistory, RiskResponse, ResponseStatus, RiskStatus
from app.models.user import User, UserRole
from app.schemas.risk import AssessmentCreate, ResponseCreate, ResponseUpdate, RiskCreate, RiskUpdate
from app.services import events


# Fields whose changes are surfaced as risk.changed notifications.
# "owner" appears in change lists only when paired with other changes (a pure
# reassignment is already reported via risk.assigned).
_TRACKED_FIELDS = {
    "status": "status",
    "title": "title",
    "category": "category",
    "description": "description",
    "threat_source": "threat_source",
    "threat_event": "threat_event",
    "vulnerability": "vulnerability",
    "affected_asset": "affected_asset",
    "review_frequency_days": "review_frequency_days",
    "next_review_date": "next_review_date",
}


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
                selectinload(Risk.responses),
                selectinload(Risk.history),
            )
            .offset(skip)
            .limit(limit)
            .all()
        )
        return {"total": total, "items": items}

    def get_risk(self, risk_id: str, current_user: User) -> Risk:
        risk = self._get_active_risk(risk_id)
        if current_user.role == UserRole.risk_owner and risk.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Risk owners can only view risks assigned to them",
            )
        return risk

    # -----------------------------------------------------------------------
    # Create
    # -----------------------------------------------------------------------

    def create_risk(self, risk_data: RiskCreate, created_by: User) -> Risk:
        kwargs = {
            "risk_id": self._generate_risk_id(),
            "title": risk_data.title,
            "description": risk_data.description,
            "threat_source": risk_data.threat_source,
            "threat_event": risk_data.threat_event,
            "vulnerability": risk_data.vulnerability,
            "affected_asset": risk_data.affected_asset,
            "category": risk_data.category,
            "owner_id": risk_data.owner_id if risk_data.owner_id else created_by.id,
            "created_by_id": created_by.id,
            "status": RiskStatus.open,
            "review_frequency_days": risk_data.review_frequency_days,
            "next_review_date": risk_data.next_review_date,
        }
        if risk_data.created_at is not None:
            kwargs["created_at"] = risk_data.created_at
        risk = Risk(**kwargs)
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

        # Only admins and security analysts may reassign ownership.
        if "owner_id" in update_fields and updated_by.role == UserRole.risk_owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Risk owners cannot reassign risk ownership",
            )

        # Pull out scoring fields before iterating — they need special handling
        new_likelihood = update_fields.pop("likelihood", None)
        new_impact = update_fields.pop("impact", None)

        # Snapshot owner_id before mutation so we can fire risk.assigned post-commit.
        owner_changed = False
        old_owner_id = risk.owner_id
        new_owner_id = old_owner_id

        # Collect the human-readable field names that changed, for risk.changed.
        changed_fields: list[str] = []

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
                if field == "owner_id":
                    owner_changed = True
                    new_owner_id = new_value
                if field in _TRACKED_FIELDS:
                    changed_fields.append(_TRACKED_FIELDS[field])

        # If either scoring value was sent, create a new assessment row
        score_changed = False
        if new_likelihood is not None or new_impact is not None:
            latest = risk.assessments[0] if risk.assessments else None
            lh = new_likelihood if new_likelihood is not None else (latest.likelihood if latest else 1)
            im = new_impact if new_impact is not None else (latest.impact if latest else 1)
            if latest is None or latest.likelihood != lh or latest.impact != im:
                score_changed = True
            self.db.add(RiskAssessment(
                risk_id=risk.id,
                likelihood=lh,
                impact=im,
                risk_score=lh * im,
                assessed_by_id=updated_by.id,
            ))
            if risk.review_frequency_days:
                risk.next_review_date = date.today() + timedelta(days=risk.review_frequency_days)

        if score_changed:
            changed_fields.append("score")

        self.db.commit()
        self.db.refresh(risk)

        # Emit risk.assigned AFTER the commit so subscribers see committed state.
        if owner_changed:
            events.emit_sync(
                "risk.assigned",
                subject={"risk_id": risk.risk_id, "title": risk.title},
                data={
                    "new_owner_id": new_owner_id,
                    "previous_owner_id": old_owner_id,
                },
                actor={"id": updated_by.id, "email": updated_by.email},
            )

        # Emit risk.changed for non-reassignment edits when actor != post-update owner.
        notify_owner_id = new_owner_id
        if changed_fields and updated_by.id != notify_owner_id:
            events.emit_sync(
                "risk.changed",
                subject={"risk_id": risk.risk_id, "title": risk.title},
                data={
                    "owner_id": notify_owner_id,
                    "changes": changed_fields,
                },
                actor={"id": updated_by.id, "email": updated_by.email},
            )

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

        latest = risk.assessments[0] if risk.assessments else None
        score_changed = (
            latest is None
            or latest.likelihood != data.likelihood
            or latest.impact != data.impact
        )

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

        if score_changed and assessed_by.id != risk.owner_id:
            events.emit_sync(
                "risk.changed",
                subject={"risk_id": risk.risk_id, "title": risk.title},
                data={"owner_id": risk.owner_id, "changes": ["score"]},
                actor={"id": assessed_by.id, "email": assessed_by.email},
            )

        return risk

    # -----------------------------------------------------------------------
    # Response (risk response / mitigation plan)
    # -----------------------------------------------------------------------

    def add_response(
        self, risk_id: str, data: ResponseCreate, created_by: User
    ) -> Risk:
        risk = self._get_active_risk(risk_id)
        self._check_edit_permission(risk, created_by)

        self.db.add(RiskResponse(
            risk_id=risk.id,
            response_type=data.response_type,
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

    def update_response(
        self, risk_id: str, response_id: int, data: ResponseUpdate, updated_by: User
    ) -> Risk:
        risk = self._get_active_risk(risk_id)
        self._check_edit_permission(risk, updated_by)

        response = (
            self.db.query(RiskResponse)
            .filter(RiskResponse.id == response_id, RiskResponse.risk_id == risk.id)
            .first()
        )
        if response is None:
            raise HTTPException(status_code=404, detail="Response not found")

        update_data = data.model_dump(exclude_unset=True)

        # Auto-stamp completion_date when transitioning to completed without an explicit date.
        if (
            update_data.get("status") == ResponseStatus.completed
            and response.status != ResponseStatus.completed
            and "completion_date" not in update_data
        ):
            update_data["completion_date"] = datetime.now(timezone.utc)

        # Clear completion_date when moving away from completed if caller didn't override.
        if (
            update_data.get("status") is not None
            and update_data["status"] != ResponseStatus.completed
            and response.status == ResponseStatus.completed
            and "completion_date" not in update_data
        ):
            update_data["completion_date"] = None

        for field, value in update_data.items():
            setattr(response, field, value)

        self.db.commit()
        self.db.refresh(risk)
        return risk

    def delete_response(self, risk_id: str, response_id: int, deleted_by: User) -> None:
        risk = self._get_active_risk(risk_id)
        self._check_edit_permission(risk, deleted_by)

        response = (
            self.db.query(RiskResponse)
            .filter(RiskResponse.id == response_id, RiskResponse.risk_id == risk.id)
            .first()
        )
        if response is None:
            raise HTTPException(status_code=404, detail="Response not found")

        self.db.delete(response)
        self.db.commit()

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

    # -----------------------------------------------------------------------
    # Bulk helper — drives per-risk iteration with per-item error capture
    # -----------------------------------------------------------------------

    def bulk_apply(
        self, risk_ids: list[str], op: Callable[[str], None]
    ) -> dict:
        """
        Iterate de-duplicated `risk_ids`, invoking `op(risk_id)` per id.
        HTTPException → captured as an error row; other exceptions roll back
        the session and propagate so the route returns 500.
        """
        seen: set[str] = set()
        unique_ids: list[str] = []
        for rid in risk_ids:
            if rid not in seen:
                seen.add(rid)
                unique_ids.append(rid)

        updated: list[str] = []
        errors: list[dict] = []
        for rid in unique_ids:
            try:
                op(rid)
                updated.append(rid)
            except HTTPException as exc:
                errors.append({"risk_id": rid, "message": str(exc.detail)})
            except Exception:
                self.db.rollback()
                raise
        return {"updated": updated, "errors": errors}
