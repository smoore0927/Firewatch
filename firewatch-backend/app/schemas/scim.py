"""SCIM 2.0 request/response schemas (RFC 7643/7644)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
SCIM_LIST_RESPONSE_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
SCIM_PATCH_OP_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
SCIM_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"


class SCIMName(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    givenName: str | None = None
    familyName: str | None = None


class SCIMEmail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    value: str
    primary: bool = True
    type: str | None = "work"


class SCIMMeta(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    resourceType: str = "User"
    created: datetime
    lastModified: datetime | None = None
    location: str | None = None


class SCIMUser(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schemas: list[str] = Field(default_factory=lambda: [SCIM_USER_SCHEMA])
    id: str | None = None
    externalId: str | None = None
    userName: str
    name: SCIMName | None = None
    emails: list[SCIMEmail] | None = None
    active: bool = True
    meta: SCIMMeta | None = None


class SCIMPatchOp(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    op: Literal["add", "replace", "remove", "Add", "Replace", "Remove"]
    path: str | None = None
    value: Any = None


class SCIMPatchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schemas: list[str] = Field(default_factory=lambda: [SCIM_PATCH_OP_SCHEMA])
    Operations: list[SCIMPatchOp]


class SCIMListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schemas: list[str] = Field(default_factory=lambda: [SCIM_LIST_RESPONSE_SCHEMA])
    totalResults: int
    startIndex: int = 1
    itemsPerPage: int
    Resources: list[SCIMUser]


class SCIMError(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schemas: list[str] = Field(default_factory=lambda: [SCIM_ERROR_SCHEMA])
    status: str
    detail: str | None = None
    scimType: str | None = None
