"""Memory read repository — find_similar with vector + GIN fallback (milestone 3.D.1)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.org_context import set_service_org
from app.read.full_text import (
    FullTextHit,
    FullTextSearchQuery,
    full_text_search,
    is_searchable_query,
)
from app.read.metrics import SEARCH_FALLBACK
from app.read.models import FindSimilarQuery, MemorySearchResult
from app.read.ranking import (
    HydratedHit,
    RankedCandidate,
    merge_candidates,
    rank_hydrated_hits,
)
from app.vectorstore.base import SearchHit, SearchRequest, VectorStore

_HYDRATE_SQL = """
SELECT id, org_id, agent_id, content, category, confidence, status,
       created_at, updated_at, valid_from, usefulness_score, retrieval_count
FROM ibex_core.memories
WHERE org_id = :org_id
  AND id = ANY(CAST(:memory_ids AS uuid[]))
  AND confidence >= :min_confidence
  AND status = 'active'
  AND deleted_at IS NULL
"""


def _validate_find_similar_query(query: FindSimilarQuery) -> None:
    if query.limit < 1:
        msg = "limit must be >= 1"
        raise ValueError(msg)
    if query.min_confidence < 0.0 or query.min_confidence > 1.0:
        msg = "min_confidence must be in [0, 1]"
        raise ValueError(msg)


def _fts_fallback_enabled(
    settings: Settings,
    *,
    vector_count: int,
    limit: int,
    query_text: str,
) -> bool:
    return (
        settings.search_fallback_enabled
        and vector_count < limit
        and is_searchable_query(query_text)
    )


class MemoryReadRepository:
    """Tenant-scoped semantic search; vector primary, GIN supplemental."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        vector_store: VectorStore,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._vector_store = vector_store
        self._settings = settings

    async def find_similar(self, query: FindSimilarQuery) -> list[MemorySearchResult]:
        _validate_find_similar_query(query)
        vector_candidates = await self._vector_candidates(query)
        vector_hydrated = await self._hydrate_hits(
            org_id=query.org_id,
            candidates=vector_candidates,
            min_confidence=query.min_confidence,
        )
        vector_ranked = rank_hydrated_hits(vector_candidates, vector_hydrated)
        if len(vector_ranked) >= query.limit:
            return vector_ranked[: query.limit]

        fts_candidates = await self._fts_candidates(query, vector_ranked=vector_ranked)
        if not fts_candidates:
            return vector_ranked

        merged = merge_candidates(vector_candidates, fts_candidates)
        fts_hydrated = await self._hydrate_hits(
            org_id=query.org_id,
            candidates=fts_candidates,
            min_confidence=query.min_confidence,
        )
        all_hydrated = {**fts_hydrated, **vector_hydrated}
        return rank_hydrated_hits(merged, all_hydrated)[: query.limit]

    async def _vector_candidates(self, query: FindSimilarQuery) -> list[RankedCandidate]:
        vector_hits = await self._vector_store.search(
            SearchRequest(
                org_id=query.org_id,
                agent_id=query.agent_id,
                query_embedding=query.query_embedding,
                limit=query.limit,
                min_similarity=query.min_similarity,
            )
        )
        return _vector_candidates(vector_hits)

    async def _fts_candidates(
        self,
        query: FindSimilarQuery,
        *,
        vector_ranked: list[MemorySearchResult],
    ) -> list[RankedCandidate]:
        if not _fts_fallback_enabled(
            self._settings,
            vector_count=len(vector_ranked),
            limit=query.limit,
            query_text=query.query_text,
        ):
            return []

        remaining = query.limit - len(vector_ranked)
        exclude = frozenset(item.id for item in vector_ranked)
        fts_hits = await full_text_search(
            self._session_factory,
            FullTextSearchQuery(
                org_id=query.org_id,
                agent_id=query.agent_id,
                query_text=query.query_text,
                limit=remaining + len(exclude),
                min_confidence=query.min_confidence,
                exclude_ids=exclude,
            ),
        )
        fts_candidates = _fts_candidates(fts_hits, cap=remaining)
        if not fts_candidates:
            return []

        SEARCH_FALLBACK.labels(triggered="true").inc()
        return fts_candidates

    async def _hydrate_hits(
        self,
        *,
        org_id: UUID,
        candidates: list[RankedCandidate],
        min_confidence: float,
    ) -> dict[UUID, HydratedHit]:
        if not candidates:
            return {}
        ids = [str(item.memory_id) for item in candidates]
        async with self._session_factory() as session, session.begin():
            await set_service_org(session, org_id)
            result = await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text  # nosec B608
                    _HYDRATE_SQL
                ),
                {
                    "org_id": str(org_id),
                    "memory_ids": ids,
                    "min_confidence": min_confidence,
                },
            )
            rows = result.mappings().all()

        score_by_id = {item.memory_id: item for item in candidates}
        out: dict[UUID, HydratedHit] = {}
        for row in rows:
            memory_id = UUID(str(row["id"]))
            ranked = score_by_id.get(memory_id)
            if ranked is None:
                continue
            out[memory_id] = HydratedHit(
                result=MemorySearchResult(
                    id=memory_id,
                    org_id=UUID(str(row["org_id"])),
                    agent_id=UUID(str(row["agent_id"])),
                    content=str(row["content"]),
                    category=str(row["category"]),
                    confidence=float(row["confidence"]),
                    status=str(row["status"]),
                    similarity=ranked.score,
                    source=ranked.source,
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                ),
                valid_from=row["valid_from"],
                usefulness_score=float(row["usefulness_score"]),
                retrieval_count=int(row["retrieval_count"]),
            )
        return out


def _vector_candidates(hits: list[SearchHit]) -> list[RankedCandidate]:
    return [
        RankedCandidate(memory_id=hit.memory_id, score=hit.similarity, source="vector")
        for hit in hits
    ]


def _fts_candidates(hits: list[FullTextHit], *, cap: int) -> list[RankedCandidate]:
    return [
        RankedCandidate(memory_id=hit.memory_id, score=hit.rank, source="full_text")
        for hit in hits[:cap]
    ]
