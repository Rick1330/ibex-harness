"""Org model-policy request/response schemas (m4.C.2 / m4.C.4).

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
_MODEL_ID_MAX = 256

_PATTERN_DESC = (
    "Go filepath.Match glob (shell-style *, ?, character classes). "
    "'*' does not match across '/'; use '*/*' or 'provider/*' for slashy model IDs."
)


def _normalize_fallback_chain(value: list[str] | None) -> list[str]:
    if not value:
        return []
    out: list[str] = []
    for raw in value:
        m = (raw or "").strip()
        if not m:
            raise ValueError("fallback_chain entries must be non-empty")
        if len(m) > _MODEL_ID_MAX:
            raise ValueError(f"fallback_chain entry exceeds {_MODEL_ID_MAX} characters")
        out.append(m)
    return out


class ModelPolicyCreate(BaseModel):
    model_pattern: str = Field(min_length=1, description=_PATTERN_DESC)
    allowed: bool
    priority: Priority = 100
    fallback_chain: list[str] = Field(default_factory=list)

    @field_validator("model_pattern")
    @classmethod
    def _pattern(cls, value: str) -> str:
        return normalize_model_pattern(value)

    @field_validator("fallback_chain")
    @classmethod
    def _chain(cls, value: list[str]) -> list[str]:
        return _normalize_fallback_chain(value)


class ModelPolicyPatch(BaseModel):
    model_pattern: str | None = Field(default=None, min_length=1, description=_PATTERN_DESC)
    allowed: bool | None = None
    priority: Priority | None = None
    fallback_chain: list[str] | None = None

    @field_validator("model_pattern")
    @classmethod
    def _pattern(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_model_pattern(value)

    @field_validator("fallback_chain")
    @classmethod
    def _chain(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _normalize_fallback_chain(value)


class ModelPolicyResponse(BaseModel):
    id: UUID
    org_id: UUID
    model_pattern: str
    allowed: bool
    priority: int
    fallback_chain: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
