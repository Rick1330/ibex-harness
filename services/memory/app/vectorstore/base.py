"""VectorStore ABC and shared search/upsert request models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, Field


class SearchHit(BaseModel):
    """Cosine-similarity hit from a vector search."""

    memory_id: UUID
    similarity: float = Field(ge=-1.0, le=1.0)


@dataclass(frozen=True, slots=True)
class UpsertRequest:
    """Embedding write against an existing memory row."""

    memory_id: UUID
    org_id: UUID
    embedding: Sequence[float]
    embedding_model: str
    embedding_dim: int = 1024

    def validate(self) -> None:
        if self.embedding_dim != 1024:
            msg = "embedding_dim must be 1024"
            raise ValueError(msg)
        if len(self.embedding) != self.embedding_dim:
            msg = (
                f"embedding length {len(self.embedding)} != embedding_dim "
                f"{self.embedding_dim}"
            )
            raise ValueError(msg)
        if not self.embedding_model.strip():
            msg = "embedding_model must be non-empty"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """Tenant-scoped vector similarity search."""

    org_id: UUID
    agent_id: UUID
    query_embedding: Sequence[float]
    limit: int
    min_similarity: float | None = None
    ef_search: int | None = None


class VectorStore(ABC):
    """Swappable embedding store — PgVectorStore is the production backend."""

    @abstractmethod
    async def upsert(self, request: UpsertRequest) -> None:
        """Store or update an embedding on an existing memory row."""

    @abstractmethod
    async def search(self, request: SearchRequest) -> list[SearchHit]:
        """Return hits ordered by descending cosine similarity."""

    @abstractmethod
    async def delete(self, *, memory_id: UUID, org_id: UUID) -> None:
        """Clear embedding fields for a memory (does not delete the row)."""
