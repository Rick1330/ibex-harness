"""POST /v1/memories request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

_CATEGORIES = Literal["factual", "preference", "behavioral", "episodic", "procedural"]
_VISIBILITY = Literal["agent", "org", "session"]


class CreateMemoryRequest(BaseModel):
    agent_id: UUID
    content: str = Field(min_length=1, max_length=10_000)
    category: _CATEGORIES = "factual"
    confidence: float = Field(default=0.80, ge=0.0, le=1.0)
    session_id: UUID | None = None
    visibility: _VISIBILITY = "agent"
    tags: list[str] = Field(default_factory=list, max_length=20)
    metadata: dict[str, Any] | None = None
    pinned: bool = False


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
    injection_risk_score: float = 0.02
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
