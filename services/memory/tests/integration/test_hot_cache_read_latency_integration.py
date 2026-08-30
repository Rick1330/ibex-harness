"""Integration latency smoke for hot cache read path (milestone 3.D.3)."""

from __future__ import annotations

import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.read.models import HotMemoryQuery
from tests.integration.hot_cache_support import (
    ScoredMemorySeed,
    flush_hot_key,
    insert_and_write_hot,
    scored_params,
    seed_org_agent_with_redis,
)

pytestmark = pytest.mark.integration

_WARMUP_ITERATIONS = 5
_TIMED_ITERATIONS = 20
_READ_LIMIT = 20
_P99_BUDGET_MS = 5.0
_SEED_COUNT = 25


def _p99_ms(samples_ms: list[float]) -> float:
    ordered = sorted(samples_ms)
    index = max(0, int(len(ordered) * 0.99) - 1)
    return ordered[index]


@pytest.mark.asyncio
async def test_hot_cache_read_latency_p99_under_budget(
    session_factory: async_sessionmaker[AsyncSession],
    settings,
) -> None:
    """Deployed Redis + Postgres hot-cache read p99 must stay within the m3.D.3 budget."""
    redis, writer, reader, org_id, agent_id = await seed_org_agent_with_redis(
        session_factory, settings
    )
    try:
        for index in range(_SEED_COUNT):
            await insert_and_write_hot(
                session_factory,
                writer,
                scored_params(
                    ScoredMemorySeed(
                        org_id=org_id,
                        agent_id=agent_id,
                        content=f"hot cache latency seed {index}",
                        age_days=float(index % 10) + 1.0,
                    )
                ),
            )

        query = HotMemoryQuery(org_id=org_id, agent_id=agent_id, limit=_READ_LIMIT)
        for _ in range(_WARMUP_ITERATIONS):
            await reader.get_hot_memories(query)

        samples_ms: list[float] = []
        for _ in range(_TIMED_ITERATIONS):
            start = time.perf_counter()
            results = await reader.get_hot_memories(query)
            samples_ms.append((time.perf_counter() - start) * 1000.0)
            assert len(results) == _READ_LIMIT

        p99 = _p99_ms(samples_ms)
        print(
            f"hot_cache_read_integration p99={p99:.3f}ms "
            f"budget={_P99_BUDGET_MS}ms limit={_READ_LIMIT}"
        )
        assert p99 < _P99_BUDGET_MS
    finally:
        await flush_hot_key(redis, org_id, agent_id)
        await redis.aclose()
