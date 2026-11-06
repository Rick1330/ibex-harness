"""Plan gates for find_similar SQL (milestone 3.D.1)."""

from __future__ import annotations

import asyncio
import time

import pytest
from ibex_async_db import parse_async_database_url
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings
from app.db import create_session_factory
from app.read.full_text import FullTextSearchQuery, full_text_search
from app.vectorstore.base import SearchRequest
from app.vectorstore.pgvector_store import PgVectorStore
from tests.integration.find_similar_support import PlanSeed, bulk_seed_for_plans
from tests.integration.plan_assert import (
    GinExplainParams,
    HnswExplainParams,
    assert_gin_index_used,
    assert_hnsw_index_scanned,
    assert_hnsw_index_used,
    explain_gin_probe_plan,
    explain_hnsw_search_plan,
    hnsw_idx_scan_count,
)

pytestmark = pytest.mark.integration

# pg_stat counters are flushed by the backend at exit or on its next stats
# interval. Under CI load the flush can lag well past 15s, so poll with a
# bounded 60s deadline instead of failing on a single early read.
_SCAN_FLUSH_TIMEOUT_SECONDS = 60.0
_SCAN_FLUSH_POLL_SECONDS = 0.25


async def _wait_for_hnsw_scan(engine: AsyncEngine, *, before: int) -> int:
    """Wait for the search backend's pg_stat counters to flush."""
    deadline = time.monotonic() + _SCAN_FLUSH_TIMEOUT_SECONDS
    while True:
        after = await hnsw_idx_scan_count(engine)
        if after > before or time.monotonic() >= deadline:
            return after
        await asyncio.sleep(_SCAN_FLUSH_POLL_SECONDS)


async def _assert_hnsw_plan(
    plan_engine: AsyncEngine,
    plan_seed: PlanSeed,
    settings: Settings,
) -> None:
    """Assert the executed search plan uses the HNSW index.

    This is the direct signal that the production query shape can use HNSW;
    the pg_stat check below additionally proves the counter path. The shared
    explain helper keeps the SQL in one reviewed place.
    """
    session_factory = create_session_factory(plan_engine)
    async with session_factory() as session, session.begin():
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.current_org_id', :org_id, true)"
            ),
            {"org_id": str(plan_seed.seeded.org_id)},
        )
        plan = await explain_hnsw_search_plan(
            session,
            HnswExplainParams(
                org_id=plan_seed.seeded.org_id,
                agent_id=plan_seed.seeded.agent_id,
                query_vec=[float(value) for value in plan_seed.query_vec],
                ef_search=settings.hnsw_ef_search,
            ),
        )
    assert_hnsw_index_used(plan)


@pytest.mark.asyncio
async def test_hnsw_index_scan_at_runtime(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    store: PgVectorStore,
    memory_database_url: str,
    settings: Settings,
) -> None:
    plan_seed = await bulk_seed_for_plans(session_factory, store)

    before = await hnsw_idx_scan_count(engine)
    target = parse_async_database_url(memory_database_url)
    plan_engine = create_async_engine(
        target.url,
        connect_args={
            **target.connect_args,
            # Force an index path so the gate verifies HNSW, not runner-specific
            # planner cost decisions between sequential and index scans.
            "server_settings": {"enable_seqscan": "off"},
        },
    )
    try:
        plan_store = PgVectorStore(create_session_factory(plan_engine), settings)
        hits = await plan_store.search(
            SearchRequest(
                org_id=plan_seed.seeded.org_id,
                agent_id=plan_seed.seeded.agent_id,
                query_embedding=plan_seed.query_vec,
                limit=10,
                min_similarity=0.0,
            )
        )
        await _assert_hnsw_plan(plan_engine, plan_seed, settings)
    finally:
        await plan_engine.dispose()
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
