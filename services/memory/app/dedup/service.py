"""Exact and near-duplicate detection for the write path (m3.C.2 / ADR-0055)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING
from uuid import UUID

from app.dedup.hash import content_hash_sha256
from app.dedup.types import DedupResult
from app.vectorstore.base import SearchRequest, VectorStore

if TYPE_CHECKING:
    from app.config import Settings

ExactLookupFn = Callable[[UUID, UUID, str], Awaitable[UUID | None]]
BumpFn = Callable[[UUID, UUID], Awaitable[int]]


class DedupService:
    """Hash exact-dedup + VectorStore near-dup candidate search."""

    def __init__(
        self,
        settings: Settings,
        *,
        store: VectorStore | None = None,
        exact_lookup: ExactLookupFn | None = None,
        bump_retrieval: BumpFn | None = None,
    ) -> None:
        self._settings = settings
        self._store = store
        self._exact_lookup = exact_lookup
        self._bump_retrieval = bump_retrieval

    def hash_content(self, content: str) -> str:
        return content_hash_sha256(content)

    async def check_exact(
        self,
        *,
        org_id: UUID,
        agent_id: UUID,
        content: str,
    ) -> DedupResult:
        content_hash = self.hash_content(content)
        if not self._settings.dedup_exact_enabled:
            return DedupResult(
                is_exact_duplicate=False,
                content_hash=content_hash,
            )
        if self._exact_lookup is None:
            msg = "exact_lookup required when dedup_exact_enabled"
            raise RuntimeError(msg)
        existing = await self._exact_lookup(org_id, agent_id, content_hash)
        if existing is None:
            return DedupResult(
                is_exact_duplicate=False,
                content_hash=content_hash,
            )
        if self._bump_retrieval is None:
            msg = "bump_retrieval required when exact duplicate is found"
            raise RuntimeError(msg)
        await self._bump_retrieval(org_id, existing)
        return DedupResult(
            is_exact_duplicate=True,
            existing_memory_id=existing,
            content_hash=content_hash,
        )

    async def find_near_duplicates(
        self,
        *,
        org_id: UUID,
        agent_id: UUID,
        embedding: Sequence[float],
    ) -> list[UUID]:
        if self._store is None:
            msg = "VectorStore required for near-duplicate search"
            raise RuntimeError(msg)
        threshold = self._settings.near_duplicate_sim_threshold
        hits = await self._store.search(
            SearchRequest(
                org_id=org_id,
                agent_id=agent_id,
                query_embedding=embedding,
                limit=self._settings.near_duplicate_candidate_limit,
                min_similarity=threshold,
            )
        )
        # Milestone gate is strict greater-than; VectorStore.search uses >=.
        return [h.memory_id for h in hits if h.similarity > threshold]
