"""Unit tests for hot cache write path (Lua trim, keys, scoring)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4

import pytest
from redis.exceptions import (
    AuthenticationError,
    AuthorizationError,
    MasterDownError,
    ResponseError,
    TryAgainError,
)
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
)
from redis.exceptions import (
    TimeoutError as RedisTimeoutError,
)

from app.cache.hot_keys import HOT_CACHE_CAPACITY, hot_memories_key
from app.cache.hot_score import compute_hot_cache_score
from app.cache.hot_write import HotZaddRequest, register_hot_zadd_trim_script, zadd_hot_memory
from app.cache.memory_keys import MEMORY_FORGOTTEN_TTL_SECONDS
from app.scoring import CompositeInputs, composite_score
from app.write.cache import (
    CacheInvalidationError,
    MemoryCacheWriter,
    is_retryable_redis_failure,
)
from app.write.models import WriteOutcome, WriteOutcomeKind
from tests.unit.memory_test_support import sample_memory_row


def test_hot_memories_key_namespaces_org_and_agent() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    assert hot_memories_key(org_id, agent_id) == f"{org_id}:hot_memories:{agent_id}"


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
            forgotten_key="org:memory_forgotten:memory",
            memory_id=memory_id,
            score=0.88,
            ttl_seconds=3600,
        ),
    )
    script.assert_awaited_once_with(
        keys=["org:hot_memories:agent", "org:memory_forgotten:memory"],
        args=[0.88, str(memory_id), 3600],
    )
    assert card == 3


def _writer_with_scripts(
    redis: MagicMock, *, guard_result: int = 1
) -> tuple[MemoryCacheWriter, AsyncMock, AsyncMock]:
    """A writer whose guard and hot scripts are recorded separately."""
    guard = AsyncMock(return_value=guard_result)
    hot = AsyncMock(return_value=1)

    def register(source: str) -> AsyncMock:
        # Both scripts check EXISTS, so the write verb is the discriminator.
        return hot if "ZADD" in source else guard

    redis.register_script = MagicMock(side_effect=register)
    redis.delete = AsyncMock()
    redis.zrem = AsyncMock()
    redis.set = AsyncMock()
    return MemoryCacheWriter(redis, MagicMock(memory_cache_ttl_seconds=3600)), guard, hot


@pytest.mark.asyncio
async def test_cache_writer_writes_through_the_guard_then_the_hot_script() -> None:
    """The object write is one atomic script; the hot write is the existing Lua."""
    from app.scoring import RankWeights

    redis = MagicMock()
    writer, guard, hot = _writer_with_scripts(redis)
    writer.settings.rank_weights.return_value = RankWeights()
    row = sample_memory_row()

    await writer.write_created(WriteOutcome(kind=WriteOutcomeKind.CREATED, memory=row))

    redis.set.assert_not_awaited()
    guard.assert_awaited_once()
    guard_args = guard.await_args
    assert guard_args is not None
    assert guard_args.kwargs["keys"] == [
        writer.object_key(row.org_id, row.id),
        writer.forgotten_key(row.org_id, row.id),
    ]
    payload = json.loads(guard_args.kwargs["args"][0])
    assert payload["content"] == row.content
    assert guard_args.kwargs["args"][1] == 3600
    hot.assert_awaited_once()
    call_args = hot.await_args
    assert call_args is not None
    assert call_args.kwargs["keys"] == [
        writer.hot_key(row.org_id, row.agent_id),
        writer.forgotten_key(row.org_id, row.id),
    ], "the hot write must check the forgotten marker in the same script"
    assert call_args.kwargs["args"][0] == pytest.approx(
        compute_hot_cache_score(row, weights=RankWeights())
    )
    assert call_args.kwargs["args"][1] == str(row.id)
    assert call_args.kwargs["args"][2] == 3600


@pytest.mark.asyncio
async def test_write_created_does_not_restore_a_forgotten_memory() -> None:
    """A delayed after-commit write loses to the forget marker and writes nothing.

    This is A1 at the writer boundary: the guard script reports the marker is
    present, so the object is not written and the hot member is not re-added.
    The atomicity itself is proved against real Redis in
    ``tests/integration/test_forget_cache_guard.py``.
    """
    redis = MagicMock()
    writer, guard, hot = _writer_with_scripts(redis, guard_result=0)
    row = sample_memory_row()

    await writer.write_created(WriteOutcome(kind=WriteOutcomeKind.CREATED, memory=row))

    guard.assert_awaited_once()
    hot.assert_not_awaited()
    redis.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_hot_write_checks_the_marker_in_the_same_script() -> None:
    """A delayed hot write is refused by the marker, exactly like the object write.

    The object guard can pass and the forget can run before ``refresh_hot``: the
    hot script is then the last writer, and it must see the marker and return 0
    without adding the member. Passing the marker as KEYS[2] is what lets the
    script decide; a ZADD with no marker check would re-add it.
    """
    redis = MagicMock()
    writer, _guard, hot = _writer_with_scripts(redis)
    hot.return_value = 0
    row = sample_memory_row()

    await writer.refresh_hot(row)

    call_args = hot.await_args
    assert call_args is not None
    assert call_args.kwargs["keys"][1] == writer.forgotten_key(row.org_id, row.id)
    assert hot.await_count == 1


def test_register_hot_zadd_trim_script() -> None:
    redis = MagicMock()
    register_hot_zadd_trim_script(redis)
    redis.register_script.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_hot_fail_open_on_redis_error() -> None:
    from redis.exceptions import RedisError

    redis = MagicMock()
    redis.register_script = MagicMock(side_effect=RedisError("boom"))
    writer = MemoryCacheWriter(redis, MagicMock(memory_cache_ttl_seconds=3600))
    row = sample_memory_row()
    await writer.refresh_hot(row)  # must not raise
    redis.register_script.assert_called_once()


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        (OSError("socket closed"), True),
        (TimeoutError(), True),
        (RedisTimeoutError("slow"), True),
        (RedisConnectionError("down"), True),
        (TryAgainError("retry"), True),
        (MasterDownError("failover"), True),
        (AuthenticationError("bad password"), False),
        (AuthorizationError("denied"), False),
        (ResponseError("WRONGTYPE"), False),
    ],
)
def test_redis_failure_retryability(error: BaseException, retryable: bool) -> None:
    """Only an outage is retried; auth and wrong-type failures are recorded now."""
    assert is_retryable_redis_failure(error) is retryable


@pytest.mark.asyncio
async def test_forget_memory_marks_the_forgotten_key_before_deleting() -> None:
    """The marker is written first, so a guarded write cannot win the race."""
    redis = MagicMock()
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    redis.zrem = AsyncMock()
    writer = MemoryCacheWriter(redis, MagicMock())
    org_id, agent_id, memory_id = uuid4(), uuid4(), uuid4()

    await writer.forget_memory(org_id=org_id, agent_id=agent_id, memory_id=memory_id)

    redis.set.assert_awaited_once_with(
        f"{org_id}:memory_forgotten:{memory_id}",
        "1",
        ex=MEMORY_FORGOTTEN_TTL_SECONDS,
    )
    redis.delete.assert_awaited_once_with(f"{org_id}:memory:{memory_id}")
    redis.zrem.assert_awaited_once_with(f"{org_id}:hot_memories:{agent_id}", str(memory_id))
    assert redis.method_calls == [
        call.set(
            f"{org_id}:memory_forgotten:{memory_id}",
            "1",
            ex=MEMORY_FORGOTTEN_TTL_SECONDS,
        ),
        call.delete(f"{org_id}:memory:{memory_id}"),
        call.zrem(f"{org_id}:hot_memories:{agent_id}", str(memory_id)),
    ]


@pytest.mark.asyncio
async def test_forget_memory_raises_so_the_caller_can_record_it() -> None:
    """A cache eviction failure is a disclosure, not a warning to drop.

    The old contract swallowed ``RedisError`` and returned, so
    ``invalidate_forgotten_memory`` could not tell a failed eviction from a
    successful one and the forget reported a clean result while the cached
    object still carried the content. The writer now raises a typed error; the
    caller retries it and records exhaustion in the erasure ledger.
    """
    redis = MagicMock()
    redis.set = AsyncMock(side_effect=ResponseError("WRONGTYPE"))
    redis.delete = AsyncMock()
    redis.zrem = AsyncMock()
    writer = MemoryCacheWriter(redis, MagicMock())
    with pytest.raises(CacheInvalidationError) as raised:
        await writer.forget_memory(org_id=uuid4(), agent_id=uuid4(), memory_id=uuid4())
    assert raised.value.retryable is False, "a wrong-type error cannot succeed on retry"
    redis.delete.assert_not_awaited()
    redis.zrem.assert_not_awaited()


@pytest.mark.asyncio
async def test_forget_memory_marks_a_transport_failure_retryable() -> None:
    redis = MagicMock()
    redis.set = AsyncMock(side_effect=RedisConnectionError("down"))
    redis.delete = AsyncMock()
    redis.zrem = AsyncMock()
    writer = MemoryCacheWriter(redis, MagicMock())
    with pytest.raises(CacheInvalidationError) as raised:
        await writer.forget_memory(org_id=uuid4(), agent_id=uuid4(), memory_id=uuid4())
    assert raised.value.retryable is True


async def test_forget_memory_raises_when_the_hot_member_removal_fails() -> None:
    """A half-evicted memory is not evicted: the member is still in the hot set."""
    from redis.exceptions import RedisError

    redis = MagicMock()
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    redis.zrem = AsyncMock(side_effect=RedisError("down"))
    writer = MemoryCacheWriter(redis, MagicMock())
    with pytest.raises(CacheInvalidationError):
        await writer.forget_memory(org_id=uuid4(), agent_id=uuid4(), memory_id=uuid4())
    redis.set.assert_awaited_once()
    redis.delete.assert_awaited_once()
    redis.zrem.assert_awaited_once()

