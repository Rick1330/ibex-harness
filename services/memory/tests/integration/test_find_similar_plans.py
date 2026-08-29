"""Plan gates for find_similar SQL (milestone 3.D.1)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.vectorstore.base import SearchRequest
from app.vectorstore.pgvector_store import PgVectorStore
from tests.integration.conftest import with_service_org
from tests.integration.find_similar_support import bulk_seed_for_plans
from tests.integration.plan_assert import (
    GinExplainParams,
    assert_gin_index_used,
    assert_hnsw_index_scanned,
    explain_gin_search_plan,
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
async def test_gin_index_used_at_runtime(
    session_factory: async_sessionmaker[AsyncSession],
    store: PgVectorStore,
) -> None:
    plan_seed = await bulk_seed_for_plans(session_factory, store)

    async with session_factory() as session, session.begin():
        await with_service_org(session, plan_seed.seeded.org_id)
        explain_json = await explain_gin_search_plan(
            session,
            GinExplainParams(
                org_id=plan_seed.seeded.org_id,
                agent_id=plan_seed.seeded.agent_id,
                query_text=plan_seed.gin_query_text,
            ),
        )

    summary = assert_gin_index_used(explain_json)
    assert int(summary.get("actual_rows") or 0) >= 1
