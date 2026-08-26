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
        _require_default_embedding_dim(self.embedding_dim)
        _require_embedding_length(self.embedding, self.embedding_dim, "embedding")
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
        _require_embedding_length(self.query_embedding, embedding_dim, "query_embedding")
        _require_at_least_one(self.limit, "limit")
        _require_unit_interval(self.min_similarity, "min_similarity")
        if self.ef_search is not None:
            _require_at_least_one(self.ef_search, "ef_search")


def _require_default_embedding_dim(embedding_dim: int) -> None:
    if embedding_dim != _DEFAULT_EMBEDDING_DIM:
        msg = "embedding_dim must be 1024"
        raise ValueError(msg)


def _require_embedding_length(
    values: Sequence[float], expected: int, field_name: str
) -> None:
    if len(values) != expected:
        msg = f"{field_name} length {len(values)} != embedding_dim {expected}"
        raise ValueError(msg)


def _require_at_least_one(value: int, field_name: str) -> None:
    if value < 1:
        msg = f"{field_name} must be >= 1"
        raise ValueError(msg)


def _require_unit_interval(value: float | None, field_name: str) -> None:
    if value is None:
        return
    if value < 0.0:
        msg = f"{field_name} must be in [0, 1]"
        raise ValueError(msg)
    if value > 1.0:
        msg = f"{field_name} must be in [0, 1]"
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
