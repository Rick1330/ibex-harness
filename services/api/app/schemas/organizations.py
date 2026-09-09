"""Organization request/response schemas."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

EmailAddress = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=320, pattern=r"^[^@]+@[^@]+\.[^@]+$"),
]

_MAX_SETTINGS_KEYS = 50
_MAX_SETTINGS_BYTES = 8192


def _validate_settings_bounds(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if len(value) > _MAX_SETTINGS_KEYS:
        msg = f"settings may have at most {_MAX_SETTINGS_KEYS} keys"
        raise ValueError(msg)
    encoded = json.dumps(value, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > _MAX_SETTINGS_BYTES:
        msg = f"settings serialized size must be at most {_MAX_SETTINGS_BYTES} bytes"
        raise ValueError(msg)
    return value


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    tier: str
    status: str
    billing_email: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @field_validator("settings")
    @classmethod
    def _bound_settings(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_settings_bounds(value) or {}


class OrganizationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    billing_email: EmailAddress | None = None
    settings: dict[str, Any] | None = None

    @field_validator("settings")
    @classmethod
    def _bound_settings(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return _validate_settings_bounds(value)


class OrgDeletionJobResponse(BaseModel):
    id: UUID
    org_id: UUID
    status: str
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
