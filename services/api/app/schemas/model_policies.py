"""Org model-policy request/response schemas (m4.C.2).

model_pattern soft-validates length/strip plus the shared Go golden reject
corpus. The proxy enforces full filepath.Match at policy load (ADR-0075).

filepath.Match '*' does not cross '/'; use '*/*' or 'provider/*' for slashy IDs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.model_pattern_normalize import normalize_model_pattern

Priority = Annotated[int, Field(ge=-1_000_000, le=1_000_000)]

_PATTERN_DESC = (
    "Go filepath.Match glob (shell-style *, ?, character classes). "
    "'*' does not match across '/'; use '*/*' or 'provider/*' for slashy model IDs."
)


class ModelPolicyCreate(BaseModel):
    model_pattern: str = Field(min_length=1, description=_PATTERN_DESC)
    allowed: bool
    priority: Priority = 100

    @field_validator("model_pattern")
    @classmethod
    def _pattern(cls, value: str) -> str:
        return normalize_model_pattern(value)


class ModelPolicyPatch(BaseModel):
    model_pattern: str | None = Field(default=None, min_length=1, description=_PATTERN_DESC)
    allowed: bool | None = None
    priority: Priority | None = None

    @field_validator("model_pattern")
    @classmethod
    def _pattern(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_model_pattern(value)


class ModelPolicyResponse(BaseModel):
    id: UUID
    org_id: UUID
    model_pattern: str
    allowed: bool
    priority: int
    created_at: datetime
    updated_at: datetime
