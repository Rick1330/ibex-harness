"""Metadata-only operator memory read models.

The projection deliberately omits ``org_id``, content, content hashes,
embeddings, and free-form metadata. Content access is a separate raw-read
contract; the metadata session used by these routes does not grant it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

MemoryStatus = Literal[
    "active",
    "superseded",
    "merged_into",
    "archived",
    "quarantined",
    "deleted",
]
MemoryCategory = Literal[
    "factual",
    "preference",
    "behavioral",
    "episodic",
    "procedural",
]


class OperatorMemory(BaseModel):
    id: UUID
    agent_id: UUID
    session_id: UUID | None = None
    category: MemoryCategory
    status: MemoryStatus
    source: str
    confidence: float
    usefulness_score: float
    content_tokens: int
    retrieval_count: int
    last_retrieved_at: datetime | None = None
    pii_detected: bool
    pii_redacted: bool
    visibility: str
    pinned: bool
    tags: list[str] = Field(default_factory=list)
    lifecycle_revision: int
    tombstoned: bool
    expires_at: datetime | None = None
    valid_from: datetime
    valid_until: datetime | None = None
    observed_at: datetime
    created_at: datetime
    updated_at: datetime


class OperatorMemoryListQuery(BaseModel):
    agent_id: UUID | None = None
    session_id: UUID | None = None
    status: MemoryStatus | None = None
    category: MemoryCategory | None = None
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=100)
