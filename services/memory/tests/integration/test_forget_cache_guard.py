"""A delayed create must not restore the object a forget just removed (A1).

Why this file exists: ``MemoryCacheWriter.write_created`` runs after the create
transaction commits. A forget can commit, tombstone the memory and delete the
cached object between that commit and the after-commit write, and the write then
recreates the object with the original content. ``_stage_cache``'s absence check
does not close it either: a create whose write is delayed past the worker's check
wins the same way.

The fix is a forgotten marker plus a check-and-set performed as one Redis script.
Redis runs a script atomically, so there is no interleaving between the marker
check and the ``SET``:

* if the forget's marker is written first, the write script sees it and writes
  nothing;
* if the write script runs first, the forget's ``DEL`` (which always follows its
  own marker ``SET``) removes the object.

This suite drives real Redis, because the atomicity is Redis's, not the mock's.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis

from app.cache.memory_keys import MEMORY_FORGOTTEN_TTL_SECONDS
from app.config import Settings
from app.write.cache import MemoryCacheWriter
from app.write.models import WriteOutcome, WriteOutcomeKind
from tests.integration.hot_cache_support import require_redis_url
from tests.unit.memory_test_support import sample_memory_row

pytestmark = pytest.mark.integration


@dataclass(frozen=True, slots=True)
class _Copy:
    """The identifiers one cached copy is addressed by."""

    org_id: UUID
    agent_id: UUID
    memory_id: UUID


async def _clear(redis: Redis, writer: MemoryCacheWriter, copy: _Copy) -> None:
    await redis.delete(
        writer.object_key(copy.org_id, copy.memory_id),
        writer.forgotten_key(copy.org_id, copy.memory_id),
        writer.hot_key(copy.org_id, copy.agent_id),
    )


async def _writer_with_redis() -> tuple[Redis, MemoryCacheWriter]:
    url = require_redis_url()
    redis = Redis.from_url(url)
    return redis, MemoryCacheWriter(redis, Settings(redis_url=url))


@pytest.mark.asyncio
async def test_a_delayed_create_cannot_restore_a_forgotten_object() -> None:
    """The exact A1 sequence: create commits, forget runs, create's write lands.

    The forget-side eviction and the worker's ``_stage_cache`` write the same
    marker before deleting, so ``EXISTS == 0`` below is the state both of them
    observe before a delayed write can run. That write is the last step: it must
    find the marker and refuse. The worker's marker-before-delete order is pinned
    in ``test_cache_stage_deletes_the_entry_and_waits_for_absence``.
    """
    redis, writer = await _writer_with_redis()
    copy = _Copy(org_id=uuid4(), agent_id=uuid4(), memory_id=uuid4())
    row = sample_memory_row(
        id=copy.memory_id,
        org_id=copy.org_id,
        agent_id=copy.agent_id,
        content="forgotten secret",
    )
    outcome = WriteOutcome(kind=WriteOutcomeKind.CREATED, memory=row)
    key = writer.object_key(copy.org_id, copy.memory_id)
    try:
        await _clear(redis, writer, copy)
        await writer.write_created(outcome)
        assert await redis.exists(key) == 1, "fixture: the create wrote the object"

        await writer.forget_memory(
            org_id=copy.org_id, agent_id=copy.agent_id, memory_id=copy.memory_id
        )
        assert await redis.exists(key) == 0
        assert (
            await redis.zscore(
                writer.hot_key(copy.org_id, copy.agent_id), str(copy.memory_id)
            )
            is None
        )

        # The delayed after-commit write of the same create now runs.
        await writer.write_created(outcome)

        assert await redis.exists(key) == 0, (
            "a create that lost the race to its own forget restored the content"
        )
        assert (
            await redis.zscore(
                writer.hot_key(copy.org_id, copy.agent_id), str(copy.memory_id)
            )
            is None
        ), "the suppressed write must not re-rank a tombstoned memory"
        marker_ttl = await redis.ttl(
            writer.forgotten_key(copy.org_id, copy.memory_id)
        )
        assert 0 < marker_ttl <= MEMORY_FORGOTTEN_TTL_SECONDS, (
            "the marker must outlive any write that was already in flight"
        )
    finally:
        await _clear(redis, writer, copy)
        await redis.aclose()


@pytest.mark.asyncio
async def test_a_write_that_wins_the_race_is_removed_by_the_forget() -> None:
    """The other ordering leaves nothing behind either."""
    redis, writer = await _writer_with_redis()
    copy = _Copy(org_id=uuid4(), agent_id=uuid4(), memory_id=uuid4())
    row = sample_memory_row(
        id=copy.memory_id,
        org_id=copy.org_id,
        agent_id=copy.agent_id,
        content="raced secret",
    )
    key = writer.object_key(copy.org_id, copy.memory_id)
    try:
        await _clear(redis, writer, copy)
        await writer.write_created(
            WriteOutcome(kind=WriteOutcomeKind.CREATED, memory=row)
        )
        assert await redis.exists(key) == 1
        await writer.forget_memory(
            org_id=copy.org_id, agent_id=copy.agent_id, memory_id=copy.memory_id
        )
        assert await redis.exists(key) == 0
    finally:
        await _clear(redis, writer, copy)
        await redis.aclose()


@pytest.mark.asyncio
async def test_concurrent_write_and_forget_always_end_absent() -> None:
    """Every interleaving ends with the object absent, which is the guarantee.

    Sequential tests cannot show that the check and the write are one step. Here
    the two commands race repeatedly; if a read-then-``SET`` had been used, some
    iteration would leave the object present after the forget.
    """
    redis, writer = await _writer_with_redis()
    try:
        for _ in range(25):
            copy = _Copy(org_id=uuid4(), agent_id=uuid4(), memory_id=uuid4())
            row = sample_memory_row(
                id=copy.memory_id,
                org_id=copy.org_id,
                agent_id=copy.agent_id,
                content="race secret",
            )
            key = writer.object_key(copy.org_id, copy.memory_id)
            await _clear(redis, writer, copy)

            await asyncio.gather(
                writer.write_created(
                    WriteOutcome(kind=WriteOutcomeKind.CREATED, memory=row)
                ),
                writer.forget_memory(
                    org_id=copy.org_id,
                    agent_id=copy.agent_id,
                    memory_id=copy.memory_id,
                ),
            )

            assert await redis.exists(key) == 0, (
                "a concurrent write survived the forget; the guard is not atomic"
            )
            await _clear(redis, writer, copy)
    finally:
        await redis.aclose()
