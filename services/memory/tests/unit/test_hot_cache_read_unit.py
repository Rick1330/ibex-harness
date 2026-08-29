"""Unit tests for MemoryHotCacheReader."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.read.hot_cache import MemoryHotCacheReader
from app.read.models import HotMemoryQuery


def _mapping_row(memory_id, org_id, agent_id):
    now = datetime.now(tz=UTC)
    return {
        "id": memory_id,
        "org_id": org_id,
        "agent_id": agent_id,
        "content": "cached content",
        "category": "factual",
        "confidence": 0.9,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }


@pytest.mark.asyncio
async def test_get_hot_memories_returns_empty_when_redis_unavailable() -> None:
    reader = MemoryHotCacheReader(None, MagicMock())
    results = await reader.get_hot_memories(
        HotMemoryQuery(org_id=uuid4(), agent_id=uuid4(), limit=10)
    )
    assert results == []


@pytest.mark.asyncio
async def test_get_hot_memories_preserves_zset_order() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    first_id = uuid4()
    second_id = uuid4()
    redis = AsyncMock()
    redis.zrevrange = AsyncMock(
        return_value=[
            (str(first_id).encode(), 0.9),
            (str(second_id).encode(), 0.7),
        ]
    )
    session = MagicMock()
    result = MagicMock()
    result.mappings.return_value.all.return_value = [
        _mapping_row(first_id, org_id, agent_id),
        _mapping_row(second_id, org_id, agent_id),
    ]
    session.execute = AsyncMock(return_value=result)
    begin = MagicMock()
    begin.__aenter__ = AsyncMock(return_value=session)
    begin.__aexit__ = AsyncMock(return_value=None)
    session.begin = MagicMock(return_value=begin)
    factory = MagicMock(return_value=MagicMock(__aenter__=AsyncMock(return_value=session), __aexit__=AsyncMock(return_value=None)))

    reader = MemoryHotCacheReader(redis, factory)
    results = await reader.get_hot_memories(
        HotMemoryQuery(org_id=org_id, agent_id=agent_id, limit=10)
    )
    assert [item.id for item in results] == [first_id, second_id]
    assert results[0].source == "hot_cache"
    assert results[0].similarity == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_get_hot_memories_filters_stale_ids_on_hydrate() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    present_id = uuid4()
    missing_id = uuid4()
    redis = AsyncMock()
    redis.zrevrange = AsyncMock(
        return_value=[
            (str(missing_id).encode(), 0.95),
            (str(present_id).encode(), 0.5),
        ]
    )
    session = MagicMock()
    result = MagicMock()
    result.mappings.return_value.all.return_value = [
        _mapping_row(present_id, org_id, agent_id),
    ]
    session.execute = AsyncMock(return_value=result)
    begin = MagicMock()
    begin.__aenter__ = AsyncMock(return_value=session)
    begin.__aexit__ = AsyncMock(return_value=None)
    session.begin = MagicMock(return_value=begin)
    factory = MagicMock(return_value=MagicMock(__aenter__=AsyncMock(return_value=session), __aexit__=AsyncMock(return_value=None)))

    reader = MemoryHotCacheReader(redis, factory)
    results = await reader.get_hot_memories(
        HotMemoryQuery(org_id=org_id, agent_id=agent_id, limit=10)
    )
    assert len(results) == 1
    assert results[0].id == present_id


@pytest.mark.asyncio
async def test_get_hot_memories_redis_error_returns_empty() -> None:
    from redis.exceptions import RedisError

    redis = AsyncMock()
    redis.zrevrange = AsyncMock(side_effect=RedisError("down"))
    reader = MemoryHotCacheReader(redis, MagicMock())
    results = await reader.get_hot_memories(
        HotMemoryQuery(org_id=uuid4(), agent_id=uuid4(), limit=5)
    )
    assert results == []
