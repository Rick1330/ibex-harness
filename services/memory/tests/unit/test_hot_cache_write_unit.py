"""Unit tests for hot cache write path (Lua trim, keys, scoring)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.cache.hot_keys import HOT_CACHE_CAPACITY, hot_memories_key
from app.cache.hot_score import compute_hot_cache_score
from app.cache.hot_write import HotZaddRequest, register_hot_zadd_trim_script, zadd_hot_memory
from app.scoring import CompositeInputs, composite_score
from app.write.cache import MemoryCacheWriter
from app.write.models import WriteOutcome, WriteOutcomeKind
from tests.unit.memory_test_support import sample_memory_row


def test_hot_memories_key_namespaces_org_and_agent() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    assert hot_memories_key(org_id, agent_id) == f"org_id:{org_id}:hot_memories:{agent_id}"


def test_hot_cache_capacity_frozen() -> None:
    assert HOT_CACHE_CAPACITY == 50


def test_compute_hot_cache_score_matches_composite_inputs() -> None:
    row = sample_memory_row(
        category="factual",
        usefulness_score=0.6,
        confidence=0.9,
        retrieval_count=5,
    )
    expected = composite_score(
        CompositeInputs(
            relevance=1.0,
            age_days=0.0,
            categories=("factual",),
            usefulness=0.6,
            confidence=0.9,
            access_frequency=0.5,
        )
    )
    assert compute_hot_cache_score(row, now=row.valid_from) == pytest.approx(expected)


@pytest.mark.asyncio
async def test_zadd_hot_memory_invokes_lua_script() -> None:
    script = AsyncMock(return_value=3)
    memory_id = uuid4()
    card = await zadd_hot_memory(
        script,
        HotZaddRequest(
            key="org:hot_memories:agent",
            memory_id=memory_id,
            score=0.88,
            ttl_seconds=3600,
        ),
    )
    script.assert_awaited_once_with(
        keys=["org:hot_memories:agent"],
        args=[0.88, str(memory_id), 3600],
    )
    assert card == 3


@pytest.mark.asyncio
async def test_cache_writer_hot_path_uses_lua_trim() -> None:
    redis = MagicMock()
    script = AsyncMock(return_value=1)
    redis.register_script = MagicMock(return_value=script)
    redis.set = AsyncMock()
    writer = MemoryCacheWriter(redis, MagicMock(memory_cache_ttl_seconds=3600))
    row = sample_memory_row()
    await writer.write_created(WriteOutcome(kind=WriteOutcomeKind.CREATED, memory=row))
    redis.set.assert_awaited_once()
    redis.register_script.assert_called_once()
    script.assert_awaited_once()
    call_args = script.await_args
    assert call_args is not None
    assert call_args.kwargs["keys"] == [writer.hot_key(row.org_id, row.agent_id)]
    assert call_args.kwargs["args"][0] == pytest.approx(compute_hot_cache_score(row))
    assert call_args.kwargs["args"][1] == str(row.id)
    assert call_args.kwargs["args"][2] == 3600


def test_register_hot_zadd_trim_script() -> None:
    redis = MagicMock()
    register_hot_zadd_trim_script(redis)
    redis.register_script.assert_called_once()
