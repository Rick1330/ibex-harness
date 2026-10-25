"""In-memory VectorStore for unit tests — proves ABC swapability."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isclose, sqrt
from uuid import UUID

from app.vectorstore.base import (
    SearchHit,
    SearchMode,
    SearchRequest,
    UpsertRequest,
    VectorStore,
)


@dataclass
class _StoredEmbedding:
    org_id: UUID
    agent_id: UUID
    embedding: tuple[float, ...]
    embedding_model: str
    embedding_dim: int
    lifecycle_revision: int
    status: str = "active"
    deleted_at: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    tombstoned: bool = False
    expires_at: datetime | None = None


@dataclass
class InMemoryVectorStore(VectorStore):
    """Dict-backed store. agent_id is recorded on upsert via optional registry."""

    _rows: dict[UUID, _StoredEmbedding] = field(default_factory=dict)
    _agents: dict[UUID, UUID] = field(default_factory=dict)
    _lifecycle: dict[
        UUID,
        tuple[
            str,
            datetime | None,
            datetime | None,
            datetime | None,
            int,
            bool,
            datetime | None,
        ],
    ] = field(default_factory=dict)
    default_min_similarity: float = 0.70
    default_ef_search: int = 64

    def bind_agent(
        self, memory_id: UUID, agent_id: UUID, *, lifecycle_revision: int
    ) -> None:
        """Register an existing memory with its observed lifecycle revision."""
        if lifecycle_revision < 1:
            raise ValueError("lifecycle_revision must be positive")
        existing = self._rows.get(memory_id)
        if existing is not None and existing.agent_id != agent_id:
            msg = f"cannot rebind agent for stored memory {memory_id}"
            raise ValueError(msg)
        self._agents[memory_id] = agent_id
        if memory_id not in self._lifecycle:
            self.set_lifecycle(memory_id, lifecycle_revision=lifecycle_revision)

    def set_lifecycle(
        self,
        memory_id: UUID,
        *,
        lifecycle_revision: int,
        status: str = "active",
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
        deleted_at: datetime | None = None,
        tombstoned: bool = False,
        expires_at: datetime | None = None,
    ) -> None:
        """Set row lifecycle metadata used to model production search fences."""
        if lifecycle_revision < 1:
            raise ValueError("lifecycle_revision must be positive")
        self._lifecycle[memory_id] = (
            status,
            valid_from,
            valid_until,
            deleted_at,
            lifecycle_revision,
            tombstoned,
            expires_at,
        )
        row = self._rows.get(memory_id)
        if row is not None:
            row.status = status
            row.valid_from = valid_from
            row.valid_until = valid_until
            row.deleted_at = deleted_at
            row.lifecycle_revision = lifecycle_revision
            row.tombstoned = tombstoned
            row.expires_at = expires_at

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
        try:
            (
                status,
                valid_from,
                valid_until,
                deleted_at,
                lifecycle_revision,
                tombstoned,
                expires_at,
            ) = self._lifecycle[request.memory_id]
        except KeyError as exc:
            raise LookupError(
                f"memory {request.memory_id} has no registered lifecycle snapshot"
            ) from exc
        if lifecycle_revision != request.expected_revision or tombstoned:
            raise LookupError(f"memory {request.memory_id} lifecycle revision is stale")
        self._rows[request.memory_id] = _StoredEmbedding(
            org_id=request.org_id,
            agent_id=agent_id,
            embedding=tuple(float(x) for x in request.embedding),
            embedding_model=request.embedding_model,
            embedding_dim=request.embedding_dim,
            status=status,
            valid_from=valid_from,
            valid_until=valid_until,
            deleted_at=deleted_at,
            lifecycle_revision=lifecycle_revision,
            tombstoned=tombstoned,
            expires_at=expires_at,
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
            similarity = self._similarity_if_visible(request, row, query, threshold)
            if similarity is not None:
                hits.append(SearchHit(memory_id=memory_id, similarity=similarity))
        hits.sort(key=lambda h: h.similarity, reverse=True)
        return hits[: request.limit]

    def _similarity_if_visible(
        self, request: SearchRequest, row: _StoredEmbedding, query: tuple[float, ...], threshold: float
    ) -> float | None:
        if row.org_id != request.org_id or row.agent_id != request.agent_id:
            return None
        if not self._row_active(row):
            return None
        if request.mode is SearchMode.USER_RETRIEVAL and not self._row_temporally_visible(row):
            return None
        similarity = _cosine_similarity(query, row.embedding)
        return similarity if similarity >= threshold else None

    @staticmethod
    def _row_active(row: _StoredEmbedding) -> bool:
        return row.status == "active" and row.deleted_at is None and not row.tombstoned

    @staticmethod
    def _row_temporally_visible(row: _StoredEmbedding) -> bool:
        now = datetime.now(tz=UTC)
        if row.valid_from is not None and row.valid_from > now:
            return False
        if row.valid_until is not None and row.valid_until <= now:
            return False
        return row.expires_at is None or row.expires_at > now

    async def delete(self, *, memory_id: UUID, org_id: UUID, expected_revision: int) -> None:
        if expected_revision < 1:
            raise ValueError("expected_revision must be positive")
        row = self._rows.get(memory_id)
        if row is None or row.org_id != org_id:
            raise LookupError(f"memory {memory_id} lifecycle revision is stale")
        status, _, _, deleted_at, lifecycle_revision, tombstoned, _ = self._lifecycle.get(
            memory_id,
            (
                row.status,
                row.valid_from,
                row.valid_until,
                row.deleted_at,
                row.lifecycle_revision,
                row.tombstoned,
                row.expires_at,
            ),
        )
        if (
            row.lifecycle_revision != expected_revision
            or lifecycle_revision != expected_revision
            or tombstoned
            or deleted_at is not None
            or status == "deleted"
        ):
            raise LookupError(f"memory {memory_id} lifecycle revision is stale")
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
