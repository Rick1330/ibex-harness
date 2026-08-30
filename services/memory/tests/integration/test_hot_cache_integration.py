"""Integration tests for hot cache trim, read order, and concurrency (m3.D.3)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cache.hot_keys import HOT_CACHE_CAPACITY, hot_memories_key
from app.cache.hot_score import compute_hot_cache_score
from app.read.hot_cache import MemoryHotCacheReader
from app.read.models import HotMemoryQuery
from app.write.cache import MemoryCacheWriter
from tests.integration.conftest import seed_org_agent_memory
from tests.integration.hot_cache_support import (
    ScoredMemorySeed,
    flush_hot_key,
    insert_and_write_hot,
    read_hot,
    require_redis_url,
    scored_params,
    seed_org_agent_with_redis,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_hot_cache_trims_to_fifty_by_score_not_insertion_order(
    session_factory: async_sessionmaker[AsyncSession],
    settings,
) -> None:
    redis, writer, reader, org_id, agent_id = await seed_org_agent_with_redis(
        session_factory, settings
    )
    try:
        high = await insert_and_write_hot(
            session_factory,
            writer,
            scored_params(
                ScoredMemorySeed(
                    org_id=org_id,
                    agent_id=agent_id,
                    content="high-score factual memory",
                    category="factual",
                    usefulness_score=0.95,
                    confidence=0.95,
                    age_days=1.0,
                )
            ),
            retrieval_count=10,
        )

        for index in range(59):
            await insert_and_write_hot(
                session_factory,
                writer,
                scored_params(
                    ScoredMemorySeed(
                        org_id=org_id,
                        agent_id=agent_id,
                        content=f"low-score filler {index}",
                        category="episodic",
                        usefulness_score=0.1,
                        confidence=0.5,
                        age_days=120.0,
                    )
                ),
            )

        key = hot_memories_key(org_id, agent_id)
        assert await redis.zcard(key) == HOT_CACHE_CAPACITY
        assert await redis.zscore(key, str(high.id)) is not None

        results = await read_hot(reader, org_id, agent_id, limit=HOT_CACHE_CAPACITY)
        assert results
        assert results[0].id == high.id
        assert results[0].source == "hot_cache"
    finally:
        await flush_hot_key(redis, org_id, agent_id)
        await redis.aclose()


@pytest.mark.asyncio
async def test_hot_cache_read_order_matches_composite_score(
    session_factory: async_sessionmaker[AsyncSession],
    settings,
) -> None:
    redis, writer, reader, org_id, agent_id = await seed_org_agent_with_redis(
        session_factory, settings
    )
    try:
        now = datetime.now(tz=UTC)
        specs = [
            ("mid scorer", "preference", 0.6, 0.8, 3, 7.0),
            ("top scorer", "factual", 0.9, 0.95, 8, 2.0),
            ("low scorer", "episodic", 0.2, 0.6, 0, 60.0),
        ]
        rows = []
        for content, category, usefulness, confidence, retrieval, age in specs:
            row = await insert_and_write_hot(
                session_factory,
                writer,
                scored_params(
                    ScoredMemorySeed(
                        org_id=org_id,
                        agent_id=agent_id,
                        content=content,
                        category=category,
                        usefulness_score=usefulness,
                        confidence=confidence,
                        age_days=age,
                    )
                ),
                retrieval_count=retrieval,
            )
            rows.append(row)

        expected_order = sorted(
            rows,
            key=lambda row: compute_hot_cache_score(row, now=now),
            reverse=True,
        )
        results = await read_hot(reader, org_id, agent_id, limit=3)
        assert [item.id for item in results] == [row.id for row in expected_order]
    finally:
        await flush_hot_key(redis, org_id, agent_id)
        await redis.aclose()


@pytest.mark.asyncio
async def test_concurrent_hot_writes_do_not_corrupt_set(
    session_factory: async_sessionmaker[AsyncSession],
    settings,
) -> None:
    redis, writer, _, org_id, agent_id = await seed_org_agent_with_redis(
        session_factory, settings
    )
    try:
        params_list = [
            scored_params(
                ScoredMemorySeed(
                    org_id=org_id,
                    agent_id=agent_id,
                    content=f"concurrent hot {index}",
                    age_days=float(index % 30) + 1.0,
                )
            )
            for index in range(80)
        ]

        async def _insert_and_write(index: int) -> None:
            await insert_and_write_hot(session_factory, writer, params_list[index])

        await asyncio.gather(*[_insert_and_write(index) for index in range(80)])
        key = hot_memories_key(org_id, agent_id)
        assert await redis.zcard(key) == HOT_CACHE_CAPACITY
    finally:
        await flush_hot_key(redis, org_id, agent_id)
        await redis.aclose()


@pytest.mark.asyncio
async def test_hot_cache_cross_tenant_key_isolation(
    session_factory: async_sessionmaker[AsyncSession],
    settings,
) -> None:
    url = require_redis_url()
    redis = Redis.from_url(url)
    org_a, agent_a, _ = await seed_org_agent_memory(session_factory, content="tenant a")
    org_b, _, _ = await seed_org_agent_memory(session_factory, content="tenant b")
    cfg = settings.model_copy(update={"redis_url": url})
    writer = MemoryCacheWriter(redis, cfg)
    reader = MemoryHotCacheReader(redis, session_factory)
    try:
        await flush_hot_key(redis, org_a, agent_a)
        row = await insert_and_write_hot(
            session_factory,
            writer,
            scored_params(
                ScoredMemorySeed(
                    org_id=org_a,
                    agent_id=agent_a,
                    content="org a hot only",
                )
            ),
        )
        assert row.id is not None
        results_b = await reader.get_hot_memories(
            HotMemoryQuery(org_id=org_b, agent_id=agent_a, limit=10)
        )
        assert results_b == []
        results_a = await reader.get_hot_memories(
            HotMemoryQuery(org_id=org_a, agent_id=agent_a, limit=10)
        )
        assert len(results_a) == 1
    finally:
        await flush_hot_key(redis, org_a, agent_a)
        await redis.aclose()
