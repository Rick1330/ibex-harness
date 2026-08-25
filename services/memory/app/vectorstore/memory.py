"""In-memory VectorStore for unit tests — proves ABC swapability."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from math import sqrt
from uuid import UUID

from app.vectorstore.base import SearchHit, VectorStore


@dataclass
class _StoredEmbedding:
    org_id: UUID
    agent_id: UUID
    embedding: tuple[float, ...]
    embedding_model: str
    embedding_dim: int


@dataclass
class InMemoryVectorStore(VectorStore):
    """Dict-backed store. agent_id is recorded on upsert via optional registry."""

    _rows: dict[UUID, _StoredEmbedding] = field(default_factory=dict)
    _agents: dict[UUID, UUID] = field(default_factory=dict)
    default_min_similarity: float = 0.70
    default_ef_search: int = 40

    def bind_agent(self, memory_id: UUID, agent_id: UUID) -> None:
        """Associate a memory with an agent (simulates row ownership for search)."""
        self._agents[memory_id] = agent_id

    async def upsert(
        self,
        *,
        memory_id: UUID,
        org_id: UUID,
        embedding: Sequence[float],
        embedding_model: str,
        embedding_dim: int = 1024,
    ) -> None:
        if embedding_dim != 1024:
            msg = "embedding_dim must be 1024"
            raise ValueError(msg)
        if len(embedding) != embedding_dim:
            msg = f"embedding length {len(embedding)} != embedding_dim {embedding_dim}"
            raise ValueError(msg)
        if not embedding_model.strip():
            msg = "embedding_model must be non-empty"
            raise ValueError(msg)
        agent_id = self._agents.get(memory_id)
        if agent_id is None:
            msg = f"bind_agent required before upsert for memory {memory_id}"
            raise KeyError(msg)
        self._rows[memory_id] = _StoredEmbedding(
            org_id=org_id,
            agent_id=agent_id,
            embedding=tuple(float(x) for x in embedding),
            embedding_model=embedding_model,
            embedding_dim=embedding_dim,
        )

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
        del ef_search  # unused in-memory; kept for ABC parity
        threshold = (
            self.default_min_similarity if min_similarity is None else min_similarity
        )
        query = tuple(float(x) for x in query_embedding)
        hits: list[SearchHit] = []
        for memory_id, row in self._rows.items():
            if row.org_id != org_id or row.agent_id != agent_id:
                continue
            sim = _cosine_similarity(query, row.embedding)
            if sim >= threshold:
                hits.append(SearchHit(memory_id=memory_id, similarity=sim))
        hits.sort(key=lambda h: h.similarity, reverse=True)
        return hits[:limit]

    async def delete(self, *, memory_id: UUID, org_id: UUID) -> None:
        row = self._rows.get(memory_id)
        if row is None:
            return
        if row.org_id != org_id:
            return
        del self._rows[memory_id]


def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        msg = "embedding dimensions must match"
        raise ValueError(msg)
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sqrt(sum(x * x for x in a))
    nb = sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)
