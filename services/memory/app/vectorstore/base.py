"""VectorStore ABC and shared search/upsert request models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, Field

_DEFAULT_EMBEDDING_DIM = 1024


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
    embedding_dim: int = _DEFAULT_EMBEDDING_DIM

    def validate(self) -> None:
        if self.embedding_dim != _DEFAULT_EMBEDDING_DIM:
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

    def validate(self, *, embedding_dim: int = _DEFAULT_EMBEDDING_DIM) -> None:
        if len(self.query_embedding) != embedding_dim:
            msg = (
                f"query_embedding length {len(self.query_embedding)} "
                f"!= embedding_dim {embedding_dim}"
            )
            raise ValueError(msg)
        if self.limit < 1:
            msg = "limit must be >= 1"
            raise ValueError(msg)
        if self.min_similarity is not None and (
            self.min_similarity < 0.0 or self.min_similarity > 1.0
        ):
            msg = "min_similarity must be in [0, 1]"
            raise ValueError(msg)
        if self.ef_search is not None and self.ef_search < 1:
            msg = "ef_search must be >= 1"
            raise ValueError(msg)


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
