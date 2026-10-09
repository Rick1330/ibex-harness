"""Latency smoke for hot cache read path (milestone 3.D.3)."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.read.hot_cache import MemoryHotCacheReader
from app.read.models import HotMemoryQuery

_WARMUP_ITERATIONS = 20
_TIMED_ITERATIONS = 200
_READ_LIMIT = 20
_P99_BUDGET_MS = 5.0


def _percentile_ms(samples_ms: list[float], percentile: float) -> float:
    ordered = sorted(samples_ms)
    index = max(0, int(len(ordered) * percentile) - 1)
    return ordered[index]


def _build_reader_with_mocks() -> tuple[MemoryHotCacheReader, HotMemoryQuery]:
    org_id = uuid4()
    agent_id = uuid4()
    ids = [uuid4() for _ in range(_READ_LIMIT)]
    redis = AsyncMock()
    redis.zrevrange = AsyncMock(
        return_value=[(str(memory_id).encode(), 0.75) for memory_id in ids]
    )
    session = MagicMock()
    result = MagicMock()
    from datetime import UTC, datetime

    now = datetime.now(tz=UTC)
    result.mappings.return_value.all.return_value = [
        {
            "id": memory_id,
            "org_id": org_id,
            "agent_id": agent_id,
            "content": "cached",
            "category": "factual",
            "confidence": 0.9,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        for memory_id in ids
    ]
    session.execute = AsyncMock(return_value=result)
    begin = MagicMock()
    begin.__aenter__ = AsyncMock(return_value=session)
    begin.__aexit__ = AsyncMock(return_value=None)
    session.begin = MagicMock(return_value=begin)
    factory = MagicMock(
        return_value=MagicMock(
            __aenter__=AsyncMock(return_value=session),
            __aexit__=AsyncMock(return_value=None),
        )
    )
    reader = MemoryHotCacheReader(redis, factory)
    query = HotMemoryQuery(org_id=org_id, agent_id=agent_id, limit=_READ_LIMIT)
    return reader, query


@pytest.mark.asyncio
async def test_hot_cache_read_latency_p99_under_budget() -> None:
    reader, query = _build_reader_with_mocks()

    for _ in range(_WARMUP_ITERATIONS):
        await reader.get_hot_memories(query)

    samples_ms: list[float] = []
    for _ in range(_TIMED_ITERATIONS):
        start = time.perf_counter()
        await reader.get_hot_memories(query)
        samples_ms.append((time.perf_counter() - start) * 1000.0)

    p99 = _percentile_ms(samples_ms, 0.99)
    print(f"hot_cache_read p99={p99:.3f}ms budget={_P99_BUDGET_MS}ms limit={_READ_LIMIT}")
    assert p99 < _P99_BUDGET_MS
