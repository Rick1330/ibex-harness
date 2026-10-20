"""Plan gates for find_similar SQL (milestone 3.D.1)."""

from __future__ import annotations

import asyncio
import time

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.read.full_text import FullTextSearchQuery, full_text_search
from app.vectorstore.base import SearchRequest
from app.vectorstore.pgvector_store import PgVectorStore
from tests.integration.find_similar_support import bulk_seed_for_plans
from tests.integration.plan_assert import (
    GinExplainParams,
    assert_gin_index_used,
    assert_hnsw_index_scanned,
    explain_gin_probe_plan,
    hnsw_idx_scan_count,
)

pytestmark = pytest.mark.integration

_SCAN_FLUSH_TIMEOUT_SECONDS = 15.0
_SCAN_FLUSH_POLL_SECONDS = 0.25


async def _wait_for_hnsw_scan(engine: AsyncEngine, *, before: int) -> int:
    """Wait for the search backend's pg_stat counters to flush."""
    deadline = time.monotonic() + _SCAN_FLUSH_TIMEOUT_SECONDS
    while True:
        after = await hnsw_idx_scan_count(engine)
        if after > before or time.monotonic() >= deadline:
            return after
        await asyncio.sleep(_SCAN_FLUSH_POLL_SECONDS)


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
    after = await _wait_for_hnsw_scan(engine, before=before)

    assert_hnsw_index_scanned(before=before, after=after)
    assert len(hits) >= 1


@pytest.mark.asyncio
async def test_gin_index_used_at_runtime(
    session_factory: async_sessionmaker[AsyncSession],
    store: PgVectorStore,
) -> None:
    plan_seed = await bulk_seed_for_plans(session_factory, store)
    probe = GinExplainParams(query_text=plan_seed.gin_query_text)
    fts_query = FullTextSearchQuery(
        org_id=plan_seed.seeded.org_id,
        agent_id=plan_seed.seeded.agent_id,
        query_text=plan_seed.gin_query_text,
        limit=10,
        min_confidence=0.0,
    )

    hits = await full_text_search(session_factory, fts_query)
    assert len(hits) >= 1

    async with session_factory() as session, session.begin():
        explain_json = await explain_gin_probe_plan(session, probe)

    summary = assert_gin_index_used(explain_json)
    assert int(summary.get("actual_rows") or 0) >= 1
