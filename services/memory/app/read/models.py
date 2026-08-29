"""Read-path domain models for semantic search (milestone 3.D.1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

SearchSource = Literal["vector", "full_text"]


@dataclass(frozen=True, slots=True)
class FindSimilarQuery:
    """Inputs for MemoryReadRepository.find_similar (milestone 3.D.1)."""

    org_id: UUID
    agent_id: UUID
    query_embedding: tuple[float, ...] | list[float]
    query_text: str
    limit: int = 10
    min_similarity: float | None = None
    min_confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class MemorySearchResult:
    """Single search hit — similarity is the retrieval metric (cosine or ts_rank_cd).

    Result ordering uses composite_score(); this field is not the composite value.
    """

    id: UUID
    org_id: UUID
    agent_id: UUID
    content: str
    category: str
    confidence: float
    status: str
    similarity: float
    source: SearchSource
    created_at: datetime
    updated_at: datetime
