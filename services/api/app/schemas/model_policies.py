"""Org model-policy request/response schemas (m4.C.2).

model_pattern uses Go path/filepath.Match grammar so the management API rejects
patterns the proxy evaluator would later fail closed on (ADR-0075).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.model_pattern_glob import normalize_model_pattern

Priority = Annotated[int, Field(ge=-1_000_000, le=1_000_000)]


class ModelPolicyCreate(BaseModel):
    # Length upper bound is enforced in normalize_model_pattern (not Field) so
    # oversize input reaches the same error path as Go ValidatePattern.
    model_pattern: str = Field(min_length=1)
    allowed: bool
    priority: Priority = 100

    @field_validator("model_pattern")
    @classmethod
    def _pattern(cls, value: str) -> str:
        return normalize_model_pattern(value)


class ModelPolicyPatch(BaseModel):
    model_pattern: str | None = Field(default=None, min_length=1)
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
