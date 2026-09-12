"""Org model-policy request/response schemas (m4.C.2)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

Priority = Annotated[int, Field(ge=-1_000_000, le=1_000_000)]


def _validate_glob_pattern(pattern: str) -> str:
    p = pattern.strip()
    if not p:
        raise ValueError("model_pattern is required")
    if len(p) > 256:
        raise ValueError("model_pattern exceeds 256 characters")
    # Soft check aligned with Go filepath.Match (reject unbalanced '[').
    if p.count("[") != p.count("]"):
        raise ValueError("model_pattern has invalid glob syntax")
    return p


class ModelPolicyCreate(BaseModel):
    model_pattern: str = Field(min_length=1, max_length=256)
    allowed: bool
    priority: Priority = 100

    @field_validator("model_pattern")
    @classmethod
    def _pattern(cls, v: str) -> str:
        return _validate_glob_pattern(v)


class ModelPolicyPatch(BaseModel):
    model_pattern: str | None = Field(default=None, min_length=1, max_length=256)
    allowed: bool | None = None
    priority: Priority | None = None

    @field_validator("model_pattern")
    @classmethod
    def _pattern(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_glob_pattern(v)


class ModelPolicyResponse(BaseModel):
    id: UUID
    org_id: UUID
    model_pattern: str
    allowed: bool
    priority: int
    created_at: datetime
    updated_at: datetime
