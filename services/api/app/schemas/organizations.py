"""Organization request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

EmailAddress = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=320, pattern=r"^[^@]+@[^@]+\.[^@]+$"),
]


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


class OrganizationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    billing_email: EmailAddress | None = None
    settings: dict[str, Any] | None = None


class OrgDeletionJobResponse(BaseModel):
    id: UUID
    org_id: UUID
    status: str
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
