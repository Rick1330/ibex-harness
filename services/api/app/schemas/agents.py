"""Agent request/response schemas."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

AgentStatus = Literal["active", "paused", "suspended", "archived"]

SlugStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=64, pattern=r"^[a-z0-9-]+$"),
]
TagStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
]

_MAX_CONFIG_KEYS = 50
_MAX_CONFIG_BYTES = 8192
_MAX_METADATA_KEYS = 50
_MAX_METADATA_BYTES = 8192
_MAX_TAGS = 32
_MAX_PROVIDER_LEN = 64
_MAX_MODEL_LEN = 128
_MAX_DESCRIPTION_LEN = 4096


def _validate_json_object_bounds(
    value: dict[str, Any] | None,
    *,
    max_keys: int,
    max_bytes: int,
    label: str,
) -> dict[str, Any] | None:
    if value is None:
        return None
    if len(value) > max_keys:
        msg = f"{label} may have at most {max_keys} keys"
        raise ValueError(msg)
    encoded = json.dumps(value, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > max_bytes:
        msg = f"{label} serialized size must be at most {max_bytes} bytes"
        raise ValueError(msg)
    return value


def _soft_provider_or_model(value: str | None, *, max_len: int, field_name: str) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        msg = f"{field_name} must be a non-empty string when provided"
        raise ValueError(msg)
    if len(stripped) > max_len:
        msg = f"{field_name} must be at most {max_len} characters"
        raise ValueError(msg)
    return stripped


def _strip_optional_description(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _bound_config(value: dict[str, Any] | None) -> dict[str, Any] | None:
    return _validate_json_object_bounds(
        value, max_keys=_MAX_CONFIG_KEYS, max_bytes=_MAX_CONFIG_BYTES, label="config"
    )


def _bound_metadata(value: dict[str, Any] | None) -> dict[str, Any] | None:
    return _validate_json_object_bounds(
        value, max_keys=_MAX_METADATA_KEYS, max_bytes=_MAX_METADATA_BYTES, label="metadata"
    )


def _bound_tags(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    if len(value) > _MAX_TAGS:
        msg = f"tags may have at most {_MAX_TAGS} entries"
        raise ValueError(msg)
    return value


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    slug: str
    name: str
    description: str | None = None
    status: AgentStatus
    default_provider: str | None = None
    default_model: str | None = None
    active_directive_version_id: UUID | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    total_sessions: int = 0
    total_memories: int = 0
    total_tokens_used: int = 0
    last_active_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class _AgentWritable(BaseModel):
    """Shared create/patch fields — validators live once to avoid Sonar clones."""

    description: str | None = Field(default=None, max_length=_MAX_DESCRIPTION_LEN)
    config: dict[str, Any] | None = None
    tags: list[TagStr] | None = Field(default=None, max_length=_MAX_TAGS)
    metadata: dict[str, Any] | None = None
    default_provider: str | None = None
    default_model: str | None = None

    @field_validator("description")
    @classmethod
    def _v_description(cls, value: str | None) -> str | None:
        return _strip_optional_description(value)

    @field_validator("config")
    @classmethod
    def _v_config(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return _bound_config(value)

    @field_validator("metadata")
    @classmethod
    def _v_metadata(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return _bound_metadata(value)

    @field_validator("tags")
    @classmethod
    def _v_tags(cls, value: list[str] | None) -> list[str] | None:
        return _bound_tags(value)

    @field_validator("default_provider")
    @classmethod
    def _v_provider(cls, value: str | None) -> str | None:
        return _soft_provider_or_model(
            value, max_len=_MAX_PROVIDER_LEN, field_name="default_provider"
        )

    @field_validator("default_model")
    @classmethod
    def _v_model(cls, value: str | None) -> str | None:
        return _soft_provider_or_model(value, max_len=_MAX_MODEL_LEN, field_name="default_model")


class AgentCreate(_AgentWritable):
    name: str = Field(min_length=1, max_length=200)
    slug: SlugStr


class AgentPatch(_AgentWritable):
    name: str | None = Field(default=None, min_length=1, max_length=200)


class AgentListQuery(BaseModel):
    """Query params for GET /v1/agents (FastAPI Query model)."""

    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=100)
    status: AgentStatus | None = None
    tags: list[TagStr] | None = Field(default=None, max_length=_MAX_TAGS)
    search: str | None = Field(default=None, max_length=200)

    @field_validator("search")
    @classmethod
    def _strip_search(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None
