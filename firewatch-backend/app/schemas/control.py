"""Compliance control framework mapping schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.schemas._datetime import serialize_utc_datetime

# Accepted mapping_type values for a risk-to-control mapping.
MAPPING_TYPES = {"mitigates", "monitors", "detects"}


class ControlFrameworkResponse(BaseModel):
    id: int
    name: str
    version: Optional[str]
    description: Optional[str]
    source_url: Optional[str] = None
    last_imported_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at")
    def _ser_created_at(self, dt: datetime) -> str:
        return serialize_utc_datetime(dt)

    @field_serializer("last_imported_at")
    def _ser_last_imported_at(self, dt: Optional[datetime]) -> str | None:
        return serialize_utc_datetime(dt) if dt is not None else None


class FrameworkImportResult(BaseModel):
    framework_name: str
    version: Optional[str] = None
    created: int
    updated: int

    model_config = ConfigDict(from_attributes=True)


class FrameworkImportUrlRequest(BaseModel):
    url: str
    framework_name: Optional[str] = None
    version: Optional[str] = None


class FrameworkUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    version: Optional[str] = None
    description: Optional[str] = None


class ControlResponse(BaseModel):
    id: int
    framework_id: int
    framework_name: str
    control_id: str
    title: str
    description: Optional[str]
    family: Optional[str]

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_control(cls, control) -> "ControlResponse":
        return cls(
            id=control.id,
            framework_id=control.framework_id,
            framework_name=control.framework.name,
            control_id=control.control_id,
            title=control.title,
            description=control.description,
            family=control.family,
        )


class RiskControlCreate(BaseModel):
    control_id: int
    mapping_type: str = Field(default="mitigates")
    notes: Optional[str] = None


class RiskControlResponse(BaseModel):
    id: int
    mapping_type: str
    notes: Optional[str]
    created_at: datetime
    control: ControlResponse

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at")
    def _ser_created_at(self, dt: datetime) -> str:
        return serialize_utc_datetime(dt)

    @classmethod
    def from_mapping(cls, mapping) -> "RiskControlResponse":
        return cls(
            id=mapping.id,
            mapping_type=mapping.mapping_type,
            notes=mapping.notes,
            created_at=mapping.created_at,
            control=ControlResponse.from_control(mapping.control),
        )
