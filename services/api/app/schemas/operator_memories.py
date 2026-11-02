"""Metadata-only operator memory read models.

The projection deliberately omits ``org_id``, content, content hashes,
embeddings, and free-form metadata. Content access is a separate raw-read
contract; the metadata session used by these routes does not grant it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

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
MemoryVisibility = Literal["agent", "org", "session"]
MemoryTag = Annotated[str, StringConstraints(min_length=1, max_length=64)]


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
    visibility: MemoryVisibility
    pinned: bool
    tags: list[MemoryTag] = Field(default_factory=list, max_length=32)
    lifecycle_revision: int
    tombstoned: bool
    expires_at: datetime | None = None
    valid_from: datetime
    valid_until: datetime | None = None
    observed_at: datetime
    created_at: datetime
    updated_at: datetime


MemoryRelationshipType = Literal[
    "supersedes",
    "contradicts",
    "specializes",
    "generalizes",
    "merged_from",
    "derived_from",
]


class OperatorMemoryLineageTarget(BaseModel):
    """A related memory, with the state a reader needs before linking to it.

    The detail route serves retained records, so a link would resolve — but a
    tombstoned or deleted target must read as such, not as a live successor.
    """

    id: UUID
    status: MemoryStatus
    tombstoned: bool


class OperatorMemoryLineageEdge(BaseModel):
    """One typed edge, with the other end's current state.

    `resolution_notes` is deliberately absent: it is free text adjacent to
    content, and the metadata projection does not read it.
    """

    memory_id: UUID
    relationship_type: MemoryRelationshipType
    confidence: float = Field(ge=0, le=1)
    created_at: datetime
    status: MemoryStatus
    tombstoned: bool


class OperatorMemoryLineage(BaseModel):
    """Why this memory is no longer current, and what replaced it.

    `tip` is the head of the supersession chain, walked by
    `resolve_supersession_tip` with a depth cap and a cycle break in SQL. It
    equals this memory when nothing superseded it, so a reader can always show a
    head rather than an empty link.
    """

    superseded_by: OperatorMemoryLineageTarget | None = None
    merged_into: OperatorMemoryLineageTarget | None = None
    tip: OperatorMemoryLineageTarget | None = None
    # Out-edges: what this memory replaced (it is the `source` of `supersedes`).
    replaces: list[OperatorMemoryLineageEdge] = Field(default_factory=list)
    # In-edges: what replaced this memory (it is the `target` of `supersedes`).
    replaced_by: list[OperatorMemoryLineageEdge] = Field(default_factory=list)
    edges_truncated: bool = False


class OperatorMemoryDetail(OperatorMemory):
    lineage: OperatorMemoryLineage


class OperatorMemoryListQuery(BaseModel):
    agent_id: UUID | None = None
    session_id: UUID | None = None
    status: MemoryStatus | None = None
    category: MemoryCategory | None = None
    cursor: str | None = Field(default=None, max_length=2048)
    limit: int = Field(default=50, ge=1, le=100)
