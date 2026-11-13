"""POST /v1/memories/search request and response schemas (milestone 3.D.1)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.limits import MAX_SEARCH_LIMIT


class SearchMemoriesRequest(BaseModel):
    agent_id: UUID
    query: str = Field(min_length=1, max_length=10_000)
    limit: int = Field(default=10, ge=1, le=MAX_SEARCH_LIMIT)
    min_similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Model-generation fence for the vector channel: only rows recorded under this
    # embedding identity are vector candidates. The full-text channels are not fenced,
    # so a keyword hit from another generation can still be returned.
    # Omitted keeps every generation eligible (historical behaviour). Without the
    # fence a query embedded by one model is scored against vectors another model
    # produced, so cosine similarity stops meaning "related".
    embedding_model: str | None = Field(
        default=None,
        max_length=256,
        description=(
            "Restricts vector candidates to memories whose vector was recorded under "
            "this embedding identity (ibex_core.memories.embedding_model: `id` or "
            "`id@revision`). Full-text results are not fenced, so a keyword hit from "
            "another generation can still be returned. Omit to search across "
            "generations."
        ),
    )

    @field_validator("embedding_model", mode="after")
    @classmethod
    def _normalize_embedding_model(cls, value: str | None) -> str | None:
        """Refuse a blank fence here, not in the store.

        A whitespace-only value would reach the vector store and raise from the query
        layer, turning a malformed request into a 500. Stripping here also guarantees
        the compared value is byte-identical to what the write path recorded.
        """
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            msg = "embedding_model must be non-empty when set"
            raise ValueError(msg)
        return trimmed


class SearchMemoryHit(BaseModel):
    id: UUID
    agent_id: UUID
    org_id: UUID
    content: str
    category: str
    confidence: float
    status: str
    created_at: datetime
    updated_at: datetime
    lifecycle_revision: int = 1
    # Unresolved conflict escalations this memory belongs to. Two hits sharing
    # one are the two sides of a pending contradiction; the read path already
    # keeps only the higher-ranked side, and the field lets the context assembly
    # apply the same rule across the hot + cold merge.
    conflict_groups: list[UUID] = Field(default_factory=list)


class SearchResultItem(BaseModel):
    memory: SearchMemoryHit
    similarity: float
    rank: int
    source: str


class SearchMemoriesData(BaseModel):
    results: list[SearchResultItem]


class SearchMemoriesResponse(BaseModel):
    data: SearchMemoriesData
