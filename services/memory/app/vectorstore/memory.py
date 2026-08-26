"""In-memory VectorStore for unit tests — proves ABC swapability."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from math import isclose, sqrt
from uuid import UUID

from app.vectorstore.base import SearchHit, SearchRequest, UpsertRequest, VectorStore


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
        existing = self._rows.get(memory_id)
        if existing is not None and existing.agent_id != agent_id:
            msg = f"cannot rebind agent for stored memory {memory_id}"
            raise ValueError(msg)
        self._agents[memory_id] = agent_id

    async def upsert(self, request: UpsertRequest) -> None:
        request.validate()
        existing = self._rows.get(request.memory_id)
        if existing is not None and existing.org_id != request.org_id:
            msg = f"memory {request.memory_id} not found for org {request.org_id}"
            raise LookupError(msg)
        agent_id = self._agents.get(request.memory_id)
        if agent_id is None:
            msg = f"bind_agent required before upsert for memory {request.memory_id}"
            raise KeyError(msg)
        self._rows[request.memory_id] = _StoredEmbedding(
            org_id=request.org_id,
            agent_id=agent_id,
            embedding=tuple(float(x) for x in request.embedding),
            embedding_model=request.embedding_model,
            embedding_dim=request.embedding_dim,
        )

    async def search(self, request: SearchRequest) -> list[SearchHit]:
        request.validate()
        _ = request.ef_search  # unused in-memory; kept for ABC parity
        threshold = (
            self.default_min_similarity
            if request.min_similarity is None
            else request.min_similarity
        )
        query = tuple(float(x) for x in request.query_embedding)
        hits: list[SearchHit] = []
        for memory_id, row in self._rows.items():
            if row.org_id != request.org_id or row.agent_id != request.agent_id:
                continue
            sim = _cosine_similarity(query, row.embedding)
            if sim >= threshold:
                hits.append(SearchHit(memory_id=memory_id, similarity=sim))
        hits.sort(key=lambda h: h.similarity, reverse=True)
        return hits[: request.limit]

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
    if isclose(na, 0.0) or isclose(nb, 0.0):
        return 0.0
    return dot / (na * nb)
