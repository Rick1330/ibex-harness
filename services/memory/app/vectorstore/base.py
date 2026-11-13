"""VectorStore ABC and shared search/upsert request models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

_DEFAULT_EMBEDDING_DIM = 1024

# ibex_core.memories.embedding_model + memories_embedding_model_len_chk (<= 256).
_EMBEDDING_MODEL_MAX_CHARS = 256


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
    expected_revision: int
    embedding_dim: int = _DEFAULT_EMBEDDING_DIM

    def validate(self) -> None:
        _require_default_embedding_dim(self.embedding_dim)
        _require_embedding_length(self.embedding, self.embedding_dim, "embedding")
        if self.expected_revision < 1:
            msg = "expected_revision must be positive"
            raise ValueError(msg)
        if not self.embedding_model.strip():
            msg = "embedding_model must be non-empty"
            raise ValueError(msg)


class SearchMode(StrEnum):
    """Purpose of a vector query; historical reads are write-path-only."""

    USER_RETRIEVAL = "user_retrieval"
    HISTORICAL_CONFLICT_CANDIDATES = "historical_conflict_candidates"


_ITERATIVE_SCAN_VALUES = frozenset({"off", "relaxed_order", "strict_order"})


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """Tenant-scoped vector similarity search.

    Historical conflict candidates are a separate internal write-path mode.
    User retrieval uses USER_RETRIEVAL by default and retains the validity fence.

    ``embedding_model`` is an optional model-generation fence: when set, only rows
    recorded under that exact ``ibex_core.memories.embedding_model`` are eligible.
    Omitted/None keeps every generation eligible, which is the historical behaviour.
    Without the fence a query embedded by model B is compared, unit for unit, against
    vectors produced by model A -- a similarity in that case is arithmetic, not meaning.
    ``memories_embedding_triplet_chk`` guarantees every embedded row names a model, so
    the fence never silently drops a vector that has no id; it only excludes generations
    recorded under a different one.
    """

    org_id: UUID
    agent_id: UUID
    query_embedding: Sequence[float]
    limit: int
    min_similarity: float | None = None
    ef_search: int | None = None
    # pgvector 0.8+: off | relaxed_order | strict_order (None = leave GUC alone)
    iterative_scan: str | None = None
    mode: SearchMode = SearchMode.USER_RETRIEVAL
    embedding_model: str | None = None

    @property
    def embedding_model_fence(self) -> str | None:
        """The fence value to bind, whitespace-trimmed; None disables the fence."""
        if self.embedding_model is None:
            return None
        return self.embedding_model.strip()

    def validate(self, *, embedding_dim: int = _DEFAULT_EMBEDDING_DIM) -> None:
        if not isinstance(self.mode, SearchMode):
            msg = f"mode must be a SearchMode, got {self.mode!r}"
            raise TypeError(msg)
        _require_embedding_length(self.query_embedding, embedding_dim, "query_embedding")
        _require_at_least_one(self.limit, "limit")
        _require_unit_interval(self.min_similarity, "min_similarity")
        if self.ef_search is not None:
            _require_at_least_one(self.ef_search, "ef_search")
        _require_optional_embedding_model(self.embedding_model)
        if self.iterative_scan is not None and self.iterative_scan not in _ITERATIVE_SCAN_VALUES:
            msg = (
                "iterative_scan must be one of "
                f"{sorted(_ITERATIVE_SCAN_VALUES)}, got {self.iterative_scan!r}"
            )
            raise ValueError(msg)


def _require_default_embedding_dim(embedding_dim: int) -> None:
    if embedding_dim != _DEFAULT_EMBEDDING_DIM:
        msg = "embedding_dim must be 1024"
        raise ValueError(msg)


def _require_embedding_length(values: Sequence[float], expected: int, field_name: str) -> None:
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


def _require_optional_embedding_model(value: str | None) -> None:
    """A model fence must be a usable identity, never an empty comparison.

    ``""`` would bind an empty string and match nothing, which reads as "no results
    for this query" rather than "your fence is wrong". Refuse it here instead.
    """
    if value is None:
        return
    trimmed = value.strip()
    if not trimmed:
        msg = "embedding_model must be non-empty when set"
        raise ValueError(msg)
    if len(trimmed) > _EMBEDDING_MODEL_MAX_CHARS:
        msg = (
            f"embedding_model must be at most {_EMBEDDING_MODEL_MAX_CHARS} characters "
            "(ibex_core.memories.embedding_model)"
        )
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
    async def delete(self, *, memory_id: UUID, org_id: UUID, expected_revision: int) -> None:
        """Clear embeddings only at the expected revision; never bypass a tombstone."""
