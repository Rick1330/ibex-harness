"""Private write-path capability for historical conflict candidate searches."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from app.vectorstore.base import SearchHit, SearchMode, SearchRequest, VectorStore


class HistoricalConflictCapability:
    """Organization/agent-fenced adapter for the only historical search path.

    This object is intentionally internal. User retrieval receives a normal
    VectorStore and cannot select the historical mode through this adapter.
    """

    def __init__(self, store: VectorStore) -> None:
        self._store = store

    async def search(
        self,
        *,
        org_id: UUID,
        agent_id: UUID,
        query_embedding: Sequence[float],
        limit: int,
        min_similarity: float | None = None,
        ef_search: int | None = None,
        iterative_scan: str | None = None,
    ) -> list[SearchHit]:
        if org_id.int == 0 or agent_id.int == 0:
            raise ValueError("historical search requires non-empty org_id and agent_id")
        request = SearchRequest(
            org_id=org_id,
            agent_id=agent_id,
            query_embedding=query_embedding,
            limit=limit,
            min_similarity=min_similarity,
            ef_search=ef_search,
            iterative_scan=iterative_scan,
            mode=SearchMode.HISTORICAL_CONFLICT_CANDIDATES,
        )
        request.validate()
        # The capability constructs both tenant fences at the same boundary
        # that selects the privileged mode; callers cannot supply a detached
        # historical request.
        if request.org_id != org_id or request.agent_id != agent_id:
            raise ValueError("historical search fence mismatch")
        return await self._store.search(request)
