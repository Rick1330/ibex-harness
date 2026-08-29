"""POST /v1/memories/search request and response schemas (milestone 3.D.1)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.limits import MAX_SEARCH_LIMIT


class SearchMemoriesRequest(BaseModel):
    agent_id: UUID
    query: str = Field(min_length=1, max_length=10_000)
    limit: int = Field(default=10, ge=1, le=MAX_SEARCH_LIMIT)
    min_similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


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


class SearchResultItem(BaseModel):
    memory: SearchMemoryHit
    similarity: float
    rank: int
    source: str


class SearchMemoriesData(BaseModel):
    results: list[SearchResultItem]


class SearchMemoriesResponse(BaseModel):
    data: SearchMemoriesData
