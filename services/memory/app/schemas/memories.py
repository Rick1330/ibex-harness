"""POST /v1/memories request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.limits import MAX_LABELS, MAX_TAGS, validate_memory_metadata, validate_tags

_CATEGORIES = Literal["factual", "preference", "behavioral", "episodic", "procedural"]
_VISIBILITY = Literal["agent", "org", "session"]


class MemoryLabelSchema(BaseModel):
    label: _CATEGORIES
    confidence: float = Field(ge=0.0, le=1.0)


class CreateMemoryRequest(BaseModel):
    agent_id: UUID
    content: str = Field(min_length=1, max_length=10_000)
    category: _CATEGORIES = "factual"
    confidence: float = Field(default=0.80, ge=0.0, le=1.0)
    labels: list[MemoryLabelSchema] | None = Field(default=None, max_length=MAX_LABELS)
    session_id: UUID | None = None
    visibility: _VISIBILITY = "agent"
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS)
    metadata: dict[str, Any] | None = None
    pinned: bool = False

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, value: list[str]) -> list[str]:
        return validate_tags(value)

    @model_validator(mode="after")
    def _validate_metadata_limits(self) -> CreateMemoryRequest:
        validate_memory_metadata(self.metadata)
        return self


class MemoryData(BaseModel):
    id: UUID
    agent_id: UUID
    org_id: UUID
    content: str
    content_tokens: int
    category: str
    confidence: float
    source: str
    status: str
    visibility: str = "agent"
    pinned: bool = False
    tags: list[str] = Field(default_factory=list)
    retrieval_count: int
    usefulness_score: float
    pii_detected: bool
    session_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class DeduplicationMeta(BaseModel):
    is_duplicate: bool = False
    similar_memories: list[UUID] = Field(default_factory=list)


class CreateMemoryMeta(BaseModel):
    deduplication: DeduplicationMeta = Field(default_factory=DeduplicationMeta)
    processing_time_ms: int
    message: str | None = None


class CreateMemoryResponse(BaseModel):
    data: MemoryData
    meta: CreateMemoryMeta


class QuarantineMemoryData(BaseModel):
    id: UUID
    status: Literal["quarantined"]
    pii_detected: bool = True


class QuarantineMemoryResponse(BaseModel):
    data: QuarantineMemoryData
    meta: dict[str, str]
