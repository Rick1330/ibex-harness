"""PgVectorStore — HNSW search with per-transaction SET LOCAL hnsw.ef_search."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.vectorstore.base import SearchHit, VectorStore


class PgVectorStore(VectorStore):
    """Production VectorStore backed by ibex_core.memories + pgvector HNSW."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings

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

        vector_literal = _vector_literal(embedding)
        async with self._session_factory() as session, session.begin():
            await _set_org(session, org_id)
            result = await session.execute(
                text(
                    """
                        UPDATE ibex_core.memories
                        SET embedding = CAST(:embedding AS vector),
                            embedding_model = :embedding_model,
                            embedding_dim = :embedding_dim,
                            updated_at = NOW()
                        WHERE id = :memory_id
                          AND org_id = :org_id
                          AND deleted_at IS NULL
                        """
                ),
                {
                    "embedding": vector_literal,
                    "embedding_model": embedding_model,
                    "embedding_dim": embedding_dim,
                    "memory_id": str(memory_id),
                    "org_id": str(org_id),
                },
            )
            if result.rowcount != 1:
                msg = f"memory {memory_id} not found for org {org_id}"
                raise LookupError(msg)

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
        if limit < 1:
            msg = "limit must be >= 1"
            raise ValueError(msg)
        threshold = (
            self._settings.vector_search_min_similarity
            if min_similarity is None
            else min_similarity
        )
        ef = self._settings.hnsw_ef_search if ef_search is None else ef_search
        if ef < 1:
            msg = "ef_search must be >= 1"
            raise ValueError(msg)

        vector_literal = _vector_literal(query_embedding)
        async with self._session_factory() as session, session.begin():
            await _set_org(session, org_id)
            await session.execute(
                text("SELECT set_config('hnsw.ef_search', :ef, true)"),
                {"ef": str(ef)},
            )
            result = await session.execute(
                text(
                    """
                        SELECT id::text AS memory_id,
                               (1 - (embedding <=> CAST(:query AS vector)))::float8
                                   AS similarity
                        FROM ibex_core.memories
                        WHERE org_id = :org_id
                          AND agent_id = :agent_id
                          AND status = 'active'
                          AND deleted_at IS NULL
                          AND embedding IS NOT NULL
                          AND (1 - (embedding <=> CAST(:query AS vector))) >= :min_similarity
                        ORDER BY embedding <=> CAST(:query AS vector)
                        LIMIT :limit
                        """
                ),
                {
                    "query": vector_literal,
                    "org_id": str(org_id),
                    "agent_id": str(agent_id),
                    "min_similarity": threshold,
                    "limit": limit,
                },
            )
            rows = result.mappings().all()
        return [
            SearchHit(memory_id=UUID(row["memory_id"]), similarity=float(row["similarity"]))
            for row in rows
        ]

    async def delete(self, *, memory_id: UUID, org_id: UUID) -> None:
        async with self._session_factory() as session, session.begin():
            await _set_org(session, org_id)
            await session.execute(
                text(
                    """
                        UPDATE ibex_core.memories
                        SET embedding = NULL,
                            embedding_model = NULL,
                            embedding_dim = NULL,
                            updated_at = NOW()
                        WHERE id = :memory_id
                          AND org_id = :org_id
                        """
                ),
                {"memory_id": str(memory_id), "org_id": str(org_id)},
            )


async def _set_org(session: AsyncSession, org_id: UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(org_id)},
    )


def _vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(str(float(v)) for v in values) + "]"
