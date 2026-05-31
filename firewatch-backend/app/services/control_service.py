"""ControlService — business logic for control framework mapping."""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.models.control import Control, ControlFramework, DeletedFrameworkSeed, RiskControl
from app.models.risk import Risk, RiskHistory
from app.models.user import User
from app.schemas.control import MAPPING_TYPES, RiskControlCreate
from app.services.control_import import ParsedFramework
from app.services.risk_service import RiskService


class ControlService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._risks = RiskService(db)

    # -----------------------------------------------------------------------
    # Frameworks / controls (catalogue reads)
    # -----------------------------------------------------------------------

    def list_frameworks(self) -> list[ControlFramework]:
        return self.db.query(ControlFramework).order_by(ControlFramework.name).all()

    def list_controls(self, framework_id: int, q: str | None = None) -> list[Control]:
        framework = self.db.query(ControlFramework).filter(ControlFramework.id == framework_id).first()
        if framework is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")

        query = (
            self.db.query(Control)
            .options(joinedload(Control.framework))
            .filter(Control.framework_id == framework_id)
        )
        if q:
            pattern = f"%{q}%"
            query = query.filter(Control.control_id.ilike(pattern) | Control.title.ilike(pattern))
        return query.order_by(Control.control_id).all()

    def delete_framework(self, framework_id: int, deleted_by: User) -> str:
        """Delete a framework (and its controls) if no risk mappings reference it.

        Blocks with 409 when any control is mapped to a risk. On success, records a
        permanent tombstone so the startup seed won't re-create it. Flushes; the route
        records the audit event and commits. Returns the deleted framework's name.
        """
        framework = (
            self.db.query(ControlFramework).filter(ControlFramework.id == framework_id).first()
        )
        if framework is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")

        mappings = (
            self.db.query(RiskControl)
            .join(Control, RiskControl.control_id == Control.id)
            .filter(Control.framework_id == framework_id)
            .all()
        )
        n_mappings = len(mappings)
        if n_mappings > 0:
            n_risks = len({m.risk_id for m in mappings})
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Framework is in use by {n_mappings} control mapping(s) "
                    f"across {n_risks} risk(s). Remove those mappings before deleting."
                ),
            )

        name = framework.name
        # Merge so a re-delete of an already-tombstoned name won't violate the unique constraint.
        self.db.merge(DeletedFrameworkSeed(name=name, deleted_by_id=deleted_by.id))
        self.db.delete(framework)
        self.db.flush()
        return name

    def update_framework(
        self,
        framework_id: int,
        *,
        name: str | None,
        version: str | None,
        description: str | None,
    ) -> ControlFramework:
        """Metadata-only edit of a framework (never touches controls)."""
        framework = (
            self.db.query(ControlFramework).filter(ControlFramework.id == framework_id).first()
        )
        if framework is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")

        if name is not None and name != framework.name:
            clash = (
                self.db.query(ControlFramework)
                .filter(ControlFramework.name == name, ControlFramework.id != framework_id)
                .first()
            )
            if clash is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A framework named '{name}' already exists.",
                )
            framework.name = name
        if version is not None:
            framework.version = version
        if description is not None:
            framework.description = description
        self.db.flush()
        return framework

    def replace_framework_controls(
        self,
        parsed: ParsedFramework,
        framework_id: int,
        *,
        version: str | None = None,
        source_url: str | None = None,
    ) -> dict:
        """Destructively replace a framework's controls from a parsed source.

        Blocks with 409 when any control is mapped to a risk. Flushes; route commits.
        """
        framework = (
            self.db.query(ControlFramework).filter(ControlFramework.id == framework_id).first()
        )
        if framework is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")

        mappings = (
            self.db.query(RiskControl)
            .join(Control, RiskControl.control_id == Control.id)
            .filter(Control.framework_id == framework_id)
            .all()
        )
        n_mappings = len(mappings)
        if n_mappings > 0:
            n_risks = len({m.risk_id for m in mappings})
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Framework is in use by {n_mappings} control mapping(s) "
                    f"across {n_risks} risk(s). Remove those mappings before replacing its controls."
                ),
            )

        self.db.query(Control).filter(Control.framework_id == framework_id).delete()

        created = 0
        for pc in parsed.controls:
            self.db.add(Control(
                framework_id=framework_id,
                control_id=pc.control_id,
                title=pc.title,
                family=pc.family,
                description=pc.description,
            ))
            created += 1

        ver = version or parsed.version
        if ver is not None:
            framework.version = ver
        framework.last_imported_at = datetime.now(timezone.utc)
        if source_url is not None:
            framework.source_url = source_url
        self.db.flush()
        return {
            "framework_name": framework.name,
            "version": framework.version,
            "created": created,
            "updated": 0,
        }

    # -----------------------------------------------------------------------
    # Risk mappings
    # -----------------------------------------------------------------------

    def list_risk_controls(self, risk_id: str, current_user: User) -> list[RiskControl]:
        risk = self._risks.get_risk(risk_id=risk_id, current_user=current_user)
        return (
            self.db.query(RiskControl)
            .options(joinedload(RiskControl.control).joinedload(Control.framework))
            .filter(RiskControl.risk_id == risk.id)
            .order_by(RiskControl.created_at.desc(), RiskControl.id.desc())
            .all()
        )

    def add_mapping(self, risk_id: str, data: RiskControlCreate, created_by: User) -> RiskControl:
        risk = self._risks._get_active_risk(risk_id)
        self._risks._check_edit_permission(risk, created_by)

        if data.mapping_type not in MAPPING_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"mapping_type must be one of {sorted(MAPPING_TYPES)}",
            )

        control = self.db.query(Control).filter(Control.id == data.control_id).first()
        if control is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control not found")

        existing = (
            self.db.query(RiskControl)
            .filter(RiskControl.risk_id == risk.id, RiskControl.control_id == control.id)
            .first()
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Control is already mapped to this risk",
            )

        mapping = RiskControl(
            risk_id=risk.id,
            control_id=control.id,
            mapping_type=data.mapping_type,
            notes=data.notes,
            created_by_id=created_by.id,
        )
        self.db.add(mapping)
        self.db.add(RiskHistory(
            risk_id=risk.id,
            field_changed="control_mapping",
            old_value=None,
            new_value=f"{control.control_id} ({data.mapping_type})",
            changed_by_id=created_by.id,
        ))
        self.db.commit()
        self.db.refresh(mapping)
        return mapping

    def delete_mapping(self, risk_id: str, mapping_id: int, deleted_by: User) -> None:
        risk = self._risks._get_active_risk(risk_id)
        self._risks._check_edit_permission(risk, deleted_by)

        mapping = (
            self.db.query(RiskControl)
            .options(joinedload(RiskControl.control))
            .filter(RiskControl.id == mapping_id, RiskControl.risk_id == risk.id)
            .first()
        )
        if mapping is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping not found")

        self.db.add(RiskHistory(
            risk_id=risk.id,
            field_changed="control_mapping",
            old_value=f"{mapping.control.control_id} ({mapping.mapping_type})",
            new_value=None,
            changed_by_id=deleted_by.id,
        ))
        self.db.delete(mapping)
        self.db.commit()
