"""Legal hold request/response schemas (4.P.3)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints
from typing import Annotated

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1024)]
Scope = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]


class LegalHoldCreate(BaseModel):
    reason: Reason
    scope: Scope = "org"


class LegalHoldResponse(BaseModel):
    id: UUID
    org_id: UUID
    scope: str
    reason: str
    set_by: UUID
    cleared_by: UUID | None = None
    created_at: datetime
    cleared_at: datetime | None = None
