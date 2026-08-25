"""VectorStore ABC and shared search result models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from pydantic import BaseModel, Field


class SearchHit(BaseModel):
    """Cosine-similarity hit from a vector search."""

    memory_id: UUID
    similarity: float = Field(ge=-1.0, le=1.0)


class VectorStore(ABC):
    """Swappable embedding store — PgVectorStore is the production backend."""

    @abstractmethod
    async def upsert(
        self,
        *,
        memory_id: UUID,
        org_id: UUID,
        embedding: Sequence[float],
        embedding_model: str,
        embedding_dim: int = 1024,
    ) -> None:
        """Store or update an embedding on an existing memory row."""

    @abstractmethod
    async def search(
        self,
        *,
        org_id: UUID,
        agent_id: UUID,
        query_embedding: Sequence[float],
        limit: int,
        min_similarity: float | None = None,
        ef_search: int | None = None,
    ) -> list[SearchHit]:
        """Return hits ordered by descending cosine similarity."""

    @abstractmethod
    async def delete(self, *, memory_id: UUID, org_id: UUID) -> None:
        """Clear embedding fields for a memory (does not delete the row)."""
