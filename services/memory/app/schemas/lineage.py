"""GET /v1/memories/{id}/lineage response schemas (milestone 5.B.1)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

RelationshipType = Literal[
    "supersedes",
    "contradicts",
    "specializes",
    "generalizes",
    "merged_from",
    "derived_from",
]


class LineageEndpointSchema(BaseModel):
    """The far end of an edge, with the state needed to interpret it."""

    memory_id: UUID
    status: str
    tombstoned: bool


class LineageEdgeSchema(BaseModel):
    """One edge, plus the hop that reached it.

    ``from_memory_id`` is the node the traversal arrived from, so a client can
    rebuild the chain without inferring direction from ``depth``.
    """

    source_memory_id: UUID
    target_memory_id: UUID
    relationship_type: RelationshipType
    confidence: float = Field(ge=0.0, le=1.0)
    depth: int = Field(ge=1)
    from_memory_id: UUID
    other: LineageEndpointSchema


class MemoryLineageData(BaseModel):
    memory_id: UUID
    status: str
    tombstoned: bool
    # null when the supersession chain is longer than the 5-hop resolution cap.
    supersession_tip: UUID | None
    max_depth: int = Field(ge=1, le=5)
    truncated: bool
    edges: list[LineageEdgeSchema]


class MemoryLineageResponse(BaseModel):
    data: MemoryLineageData


class LineageErrorDetail(BaseModel):
    code: str
    message: str


class LineageErrorEnvelope(BaseModel):
    """Stable HTTPException detail envelope for lineage error responses."""

    detail: LineageErrorDetail
