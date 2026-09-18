"""Capture policy schemas (4.P.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

CaptureMode = Literal["none", "metadata_only", "redacted", "full"]


class CapturePolicyCreate(BaseModel):
    mode: CaptureMode
    agent_id: UUID | None = None
    priority: int = Field(default=100, ge=0, le=1_000_000)


class CapturePolicyPatch(BaseModel):
    mode: CaptureMode | None = None
    priority: int | None = Field(default=None, ge=0, le=1_000_000)


class CapturePolicyResponse(BaseModel):
    id: UUID
    org_id: UUID
    agent_id: UUID | None = None
    mode: CaptureMode
    priority: int
    created_at: datetime
    updated_at: datetime
