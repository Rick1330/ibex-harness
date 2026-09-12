"""Org model-policy request/response schemas (m4.C.2).

model_pattern uses Go path/filepath.Match grammar so the management API rejects
patterns the proxy evaluator would later fail closed on (ADR-0075).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

Priority = Annotated[int, Field(ge=-1_000_000, le=1_000_000)]
_MAX_PATTERN_LEN = 256


def _skip_escape(pattern: str, i: int, n: int) -> tuple[int, str | None]:
    """Advance past a backslash escape; i points at the char after '\\'."""
    if i >= n:
        return i, "trailing backslash"
    return i + 1, None


def _skip_character_class(pattern: str, i: int, n: int) -> tuple[int, str | None]:
    """Advance past a [...] class; i points at the char after '['."""
    if i < n and pattern[i] == "^":
        i += 1
    if i >= n:
        return i, "unclosed character class"
    if pattern[i] == "]":
        return i, "empty character class"
    while i < n and pattern[i] != "]":
        if pattern[i] == "\\":
            i, err = _skip_escape(pattern, i + 1, n)
            if err is not None:
                return i, err
            continue
        i += 1
    if i >= n:
        return i, "unclosed character class"
    return i + 1, None


def _go_filepath_match_error(pattern: str) -> str | None:
    """Return a reason if Go ``filepath.Match`` would return ErrBadPattern."""
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        i += 1
        if ch == "\\":
            i, err = _skip_escape(pattern, i, n)
            if err is not None:
                return err
            continue
        if ch != "[":
            continue
        i, err = _skip_character_class(pattern, i, n)
        if err is not None:
            return err
    return None


def _normalize_model_pattern(pattern: str) -> str:
    normalized = pattern.strip()
    if not normalized:
        raise ValueError("model_pattern is required")
    if len(normalized) > _MAX_PATTERN_LEN:
        raise ValueError(f"model_pattern exceeds {_MAX_PATTERN_LEN} characters")
    reason = _go_filepath_match_error(normalized)
    if reason is not None:
        raise ValueError(f"model_pattern has invalid glob syntax ({reason})")
    return normalized


class ModelPolicyCreate(BaseModel):
    # Length upper bound is enforced in _normalize_model_pattern (not Field) so
    # oversize input reaches the same error path as Go ValidatePattern.
    model_pattern: str = Field(min_length=1)
    allowed: bool
    priority: Priority = 100

    @field_validator("model_pattern")
    @classmethod
    def _pattern(cls, value: str) -> str:
        return _normalize_model_pattern(value)


class ModelPolicyPatch(BaseModel):
    model_pattern: str | None = Field(default=None, min_length=1)
    allowed: bool | None = None
    priority: Priority | None = None

    @field_validator("model_pattern")
    @classmethod
    def _pattern(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_model_pattern(value)


class ModelPolicyResponse(BaseModel):
    id: UUID
    org_id: UUID
    model_pattern: str
    allowed: bool
    priority: int
    created_at: datetime
    updated_at: datetime
