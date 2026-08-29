"""pg_stat plan gates for find_similar SQL (milestone 3.D.1)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.read.full_text import FullTextSearchQuery
from app.vectorstore.base import SearchRequest
from app.vectorstore.pgvector_store import PgVectorStore
from tests.integration.find_similar_support import (
    bulk_seed_for_plans,
    full_text_search_for_plan_gate,
)
from tests.integration.plan_assert import (
    assert_gin_index_scanned,
    assert_hnsw_index_scanned,
    gin_idx_scan_count,
    hnsw_idx_scan_count,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_hnsw_index_scan_at_runtime(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    store: PgVectorStore,
) -> None:
    plan_seed = await bulk_seed_for_plans(session_factory, store)

    before = await hnsw_idx_scan_count(engine)
    hits = await store.search(
        SearchRequest(
            org_id=plan_seed.seeded.org_id,
            agent_id=plan_seed.seeded.agent_id,
            query_embedding=plan_seed.query_vec,
            limit=10,
            min_similarity=0.0,
        )
    )
    after = await hnsw_idx_scan_count(engine)

    assert_hnsw_index_scanned(before=before, after=after)
    assert len(hits) >= 1


@pytest.mark.asyncio
async def test_gin_index_scan_at_runtime(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    store: PgVectorStore,
) -> None:
    plan_seed = await bulk_seed_for_plans(session_factory, store)

    before = await gin_idx_scan_count(engine)
    hits = await full_text_search_for_plan_gate(
        session_factory,
        FullTextSearchQuery(
            org_id=plan_seed.seeded.org_id,
            agent_id=plan_seed.seeded.agent_id,
            query_text=plan_seed.gin_query_text,
            limit=10,
            min_confidence=0.0,
        ),
    )
    after = await gin_idx_scan_count(engine)

    assert_gin_index_scanned(before=before, after=after)
    assert len(hits) >= 1
