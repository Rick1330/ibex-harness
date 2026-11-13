"""PgVectorStore — HNSW search with per-transaction SET LOCAL hnsw.ef_search."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.org_context import set_service_org
from app.vectorstore.base import SearchHit, SearchMode, SearchRequest, UpsertRequest, VectorStore

# Shared with benchmarks/memory/plan_assert.py — keep EXPLAIN SQL in sync.
#
# The last predicate is the embedding-model fence. It is inert when the parameter is
# NULL, so an unfenced caller keeps the historical result set. It sits *inside* the
# inner select, ahead of ORDER BY / LIMIT: applied outside, it would filter the page
# after the ANN scan had already spent ``:limit`` slots on rows from other generations
# and return a short, silently incomplete page.
#
# Both occurrences are CAST to text because asyncpg prepares the statement before it
# knows the bind values: a bare ``$n IS NULL`` gives PostgreSQL nothing to infer the
# type from and the whole search fails with AmbiguousParameterError.
SEARCH_SQL = """
SELECT memory_id, similarity
FROM (
    SELECT id::text AS memory_id,
           (1 - (embedding <=> CAST(:query AS vector)))::float8 AS similarity
    FROM ibex_core.memories
    WHERE org_id = :org_id
      AND agent_id = :agent_id
      AND status = 'active'
      AND deleted_at IS NULL
      AND tombstoned = FALSE
      AND (:include_historical_candidates OR expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
      AND (:include_historical_candidates OR valid_from <= CURRENT_TIMESTAMP)
      AND (:include_historical_candidates OR valid_until IS NULL OR valid_until > CURRENT_TIMESTAMP)
      AND embedding IS NOT NULL
      AND (
          CAST(:embedding_model AS text) IS NULL
          OR embedding_model = CAST(:embedding_model AS text)
      )
    ORDER BY embedding <=> CAST(:query AS vector)
    LIMIT :limit
) ranked
WHERE similarity >= :min_similarity
ORDER BY (1 - similarity) + 0
"""


class PgVectorStore(VectorStore):
    """Production VectorStore backed by ibex_core.memories + pgvector HNSW."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings

    async def upsert(self, request: UpsertRequest) -> None:
        request.validate()
        vector_literal = _vector_literal(request.embedding)
        async with self._session_factory() as session, session.begin():
            await _set_org(session, request.org_id)
            result = await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    """
                        UPDATE ibex_core.memories
                        SET embedding = CAST(:embedding AS vector),
                            embedding_model = :embedding_model,
                            embedding_dim = :embedding_dim,
                            updated_at = NOW()
                        WHERE id = :memory_id
                          AND org_id = :org_id
                          AND deleted_at IS NULL
                          AND tombstoned = FALSE
                          AND status <> 'deleted'
                          AND lifecycle_revision = :expected_revision
                        """
                ),
                {
                    "embedding": vector_literal,
                    "embedding_model": request.embedding_model,
                    "embedding_dim": request.embedding_dim,
                    "expected_revision": request.expected_revision,
                    "memory_id": str(request.memory_id),
                    "org_id": str(request.org_id),
                },
            )
            if result.rowcount != 1:
                msg = f"memory {request.memory_id} not found for org {request.org_id}"
                raise LookupError(msg)

    async def search(self, request: SearchRequest) -> list[SearchHit]:
        """Cosine search inside one tenant, optionally inside one model generation.

        ``request.embedding_model`` adds a post-filtered model fence (NULL = every
        generation, the historical behaviour). Cost, in the honest version: HNSW
        returns ``:limit`` approximate neighbours and the fence is applied to them
        afterwards, so a window that is mostly other generations yields fewer than
        ``:limit`` rows -- recall drops for the generations that remain, and no
        re-scan widens the window because the fence is inside the ANN select.

        Plan shape, in one local run (``ibex_fresh`` fixture, 10 000 embedded rows in a
        single agent, warm cache, ``EXPLAIN (ANALYZE, BUFFERS)``): an unfenced search and
        a fence that matches rows both use ``Index Scan`` on
        ``idx_memories_embedding_hnsw`` (1.39 ms / 213 shared buffers and 0.34 ms / 182
        buffers, 10 rows each). A fence that matches no row cannot use the ANN index and
        falls back to ``Seq Scan`` on ``memories`` (7.21 ms / 516 buffers, 0 rows). Those
        timings are single observations, not a benchmark: the shape is the claim, and the
        plan gate in ``tests/integration/test_find_similar_plans.py`` enforces it. The
        worst case is a bounded scan under the tenant predicate, not an index walk over
        the whole table.

        The correct migration path during a model switch is not to widen ``:limit``:
        it is to keep one HNSW index per live generation (a partial index on
        ``embedding_model``) and route each query at its own generation's index, then
        drop the retiring index once the re-embed finishes. Until that exists, prefer
        the unfenced search inside a re-embed window and fence only after it completes.
        """
        request.validate()
        threshold = (
            self._settings.vector_search_min_similarity
            if request.min_similarity is None
            else request.min_similarity
        )
        ef = self._settings.hnsw_ef_search if request.ef_search is None else request.ef_search
        if ef < 1:
            msg = "ef_search must be >= 1"
            raise ValueError(msg)

        vector_literal = _vector_literal(request.query_embedding)
        async with self._session_factory() as session, session.begin():
            await _set_org(session, request.org_id)
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    "SELECT set_config('hnsw.ef_search', :ef, true)"
                ),
                {"ef": str(ef)},
            )
            if request.iterative_scan is not None:
                await session.execute(
                    text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                        "SELECT set_config('hnsw.iterative_scan', :mode, true)"
                    ),
                    {"mode": request.iterative_scan},
                )
            result = await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    SEARCH_SQL
                ),
                _search_params(request, vector_literal, threshold),
            )
            rows = result.mappings().all()
        return _hits(rows)

    async def delete(self, *, memory_id: UUID, org_id: UUID, expected_revision: int) -> None:
        if expected_revision < 1:
            raise ValueError("expected_revision must be positive")
        async with self._session_factory() as session, session.begin():
            await _set_org(session, org_id)
            result = await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    """
                        UPDATE ibex_core.memories
                        SET embedding = NULL,
                            embedding_model = NULL,
                            embedding_dim = NULL,
                            updated_at = NOW()
                        WHERE id = :memory_id
                          AND org_id = :org_id
                          AND lifecycle_revision = :expected_revision
                          AND tombstoned = FALSE
                          AND deleted_at IS NULL
                          AND status <> 'deleted'
                        """
                ),
                {
                    "memory_id": str(memory_id),
                    "org_id": str(org_id),
                    "expected_revision": expected_revision,
                },
            )
            if result.rowcount != 1:
                raise LookupError(
                    f"memory {memory_id} not found at expected lifecycle revision {expected_revision}"
                )


async def _set_org(session: AsyncSession, org_id: UUID) -> None:
    """Pin the tenant role and org GUC for every vector operation.

    Setting only ``app.current_org_id`` is decorative while the login role is a
    superuser: RLS is bypassed before the policy is consulted. ``set_service_org``
    runs ``SET LOCAL ROLE ibex_app`` first.
    """
    await set_service_org(session, org_id)


def _vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(str(float(v)) for v in values) + "]"


def _search_params(
    request: SearchRequest,
    vector_literal: str,
    threshold: float,
) -> dict[str, Any]:
    """Bind values for ``SEARCH_SQL``.

    ``embedding_model`` is ``request.embedding_model_fence``: None keeps every
    generation eligible, so an unfenced caller binds NULL, not a missing key.
    """
    return {
        "query": vector_literal,
        "org_id": str(request.org_id),
        "agent_id": str(request.agent_id),
        "min_similarity": threshold,
        "limit": request.limit,
        "include_historical_candidates": (
            request.mode is SearchMode.HISTORICAL_CONFLICT_CANDIDATES
        ),
        "embedding_model": request.embedding_model_fence,
    }


def _hits(rows: Sequence[Mapping[str, Any]]) -> list[SearchHit]:
    return [
        SearchHit(memory_id=UUID(row["memory_id"]), similarity=float(row["similarity"]))
        for row in rows
    ]
