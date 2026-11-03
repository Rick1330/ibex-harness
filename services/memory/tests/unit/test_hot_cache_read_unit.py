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


def _hot_reader(rows, ordered_ids, org_id, agent_id):
    redis = AsyncMock()
    redis.zrevrange = AsyncMock(
        return_value=[(str(memory_id).encode(), score) for memory_id, score in ordered_ids]
    )
    session = MagicMock()
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
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
    return MemoryHotCacheReader(redis, factory)


@pytest.mark.asyncio
async def test_get_hot_memories_preserves_zset_order() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    first_id = uuid4()
    second_id = uuid4()
    reader = _hot_reader(
        [
            _mapping_row(first_id, org_id, agent_id),
            _mapping_row(second_id, org_id, agent_id),
        ],
        [(first_id, 0.9), (second_id, 0.7)],
        org_id,
        agent_id,
    )

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
    reader = _hot_reader(
        [_mapping_row(present_id, org_id, agent_id)],
        [(missing_id, 0.95), (present_id, 0.5)],
        org_id,
        agent_id,
    )

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


@pytest.mark.asyncio
@pytest.mark.parametrize("min_confidence", [float("nan"), float("inf"), -0.1, 1.1])
async def test_get_hot_memories_rejects_bad_min_confidence(min_confidence: float) -> None:
    reader = MemoryHotCacheReader(AsyncMock(), MagicMock())
    with pytest.raises(ValueError, match="min_confidence"):
        await reader.get_hot_memories(
            HotMemoryQuery(
                org_id=uuid4(),
                agent_id=uuid4(),
                limit=10,
                min_confidence=min_confidence,
            )
        )


@pytest.mark.asyncio
async def test_get_hot_memories_maps_conflict_groups() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    memory_id = uuid4()
    group = uuid4()
    reader = _hot_reader(
        [{**_mapping_row(memory_id, org_id, agent_id), "conflict_groups": [str(group)]}],
        [(memory_id, 0.9)],
        org_id,
        agent_id,
    )

    results = await reader.get_hot_memories(
        HotMemoryQuery(org_id=org_id, agent_id=agent_id, limit=10)
    )

    assert results[0].conflict_groups == (group,)


@pytest.mark.asyncio
async def test_get_hot_memories_drops_the_lower_side_of_a_pending_conflict() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    winner, loser = uuid4(), uuid4()
    group = str(uuid4())
    reader = _hot_reader(
        [
            {**_mapping_row(winner, org_id, agent_id), "conflict_groups": [group]},
            {**_mapping_row(loser, org_id, agent_id), "conflict_groups": [group]},
        ],
        [(winner, 0.9), (loser, 0.7)],
        org_id,
        agent_id,
    )

    results = await reader.get_hot_memories(
        HotMemoryQuery(org_id=org_id, agent_id=agent_id, limit=10)
    )

    assert [item.id for item in results] == [winner]
