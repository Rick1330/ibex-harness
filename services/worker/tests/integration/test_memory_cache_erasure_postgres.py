"""Memory cache erasure: the store that carries content must be purged and proven.

Why this file exists: the object cache entry ``{org}:memory:{id}`` holds the
memory's ``content`` for up to ``memory_cache_ttl_seconds``. A forget that
tombstoned PostgreSQL and left that entry in place kept serving the memory — a
disclosure the response called "done". The forget transaction now records both
cache addresses as artifact refs, the consumer deletes them, and each store gets
a receipt, so "is anything still cached for this memory?" is answered by the
erasure ledger rather than by a log line.

What is real: PostgreSQL and Redis. The cache stages run against the real Redis
the suite is pointed at, and the unreachable case uses a genuinely dead port
rather than a stub, so ``failed`` is earned by a connection that did not answer.
The object store stays the suite's one fake.
"""

from __future__ import annotations

import pytest

from tests.integration.lifecycle_erasure_harness import (
    FakeObjectStore,
    Harness,
    OutboxSeed,
    RefSeed,
)

pytestmark = pytest.mark.integration

#: A port nothing listens on. Connecting is refused immediately, which is the
#: real "Redis is deployed but unreachable" condition the consumer must record.
_DEAD_REDIS = "redis://127.0.0.1:1/0"


@pytest.mark.asyncio
async def test_unreachable_cache_leaves_partial_then_a_retry_completes(
    harness: Harness, object_store: FakeObjectStore
) -> None:
    """A cache outage must not become a clean forget, and the next sweep fixes it.

    The first run proves the object store and the session event but cannot reach
    Redis. The row stays ``partial``, both cache receipts say ``failed`` with no
    verified timestamp, and the cached object is still there — which is exactly
    what the ledger must show an operator. A retry with Redis reachable completes
    the erasure and clears both receipts.
    """
    forgotten, row_id = await harness.seed_queued(object_store)

    first = await harness.run(ch_dsn=harness.env.ch_dsn, redis_url=_DEAD_REDIS)

    assert first["claimed"] == 1, first
    assert first["partial"] == 1, first
    assert first["complete"] == 0, "an unreachable cache is not a completed erasure"
    receipts = await harness.receipts(
        org_id=forgotten.org_id, memory_id=forgotten.memory_id
    )
    for store in ("cache", "cache_hot"):
        status, error, verified_at = receipts[store]
        assert status == "failed", (store, receipts)
        assert verified_at is None, f"{store}: a failed receipt must not be stamped"
        assert "ConnectionError" in (error or ""), (store, error)
    assert receipts["objectstore"][0] == "verified"
    assert receipts["session_event"][0] == "verified"

    state, delivered_at, _available_at, attempts = await harness.outbox(row_id=row_id)
    assert state == "partial"
    assert delivered_at is None, "a partial erasure is not delivered"
    assert attempts == 1
    assert harness.cached_object_present(forgotten), (
        "the content-bearing cache entry survived the outage; the ledger says so"
    )
    assert harness.hot_member_present(forgotten)

    await harness.make_due(row_id)
    second = await harness.run(ch_dsn=harness.env.ch_dsn)

    assert second["complete"] == 1, second
    receipts = await harness.receipts(
        org_id=forgotten.org_id, memory_id=forgotten.memory_id
    )
    assert {status for status, _error, _at in receipts.values()} == {"verified"}
    assert not harness.cached_object_present(forgotten)
    assert not harness.hot_member_present(forgotten)
    assert harness.hot_other_member_present(forgotten)
    state, delivered_at, _available, attempts = await harness.outbox(row_id=row_id)
    assert (state, delivered_at is not None, attempts) == ("complete", True, 2)


@pytest.mark.asyncio
async def test_a_completed_cache_receipt_is_written_once_per_store(
    harness: Harness, object_store: FakeObjectStore
) -> None:
    """A retried revision resumes the same two receipt rows, never duplicates.

    The unique key is the idempotency mechanism: a redelivery or a retry after a
    partial failure must update the row it already wrote. The response reads one
    row per store, so a duplicate would be invisible there and must be asserted
    on the table.
    """
    forgotten, row_id = await harness.seed_queued(object_store)

    await harness.run(ch_dsn=harness.env.ch_dsn, redis_url=_DEAD_REDIS)
    await harness.make_due(row_id)
    await harness.run(ch_dsn=harness.env.ch_dsn)
    # A further sweep claims nothing, and must still not add a row.
    assert (await harness.run(ch_dsn=harness.env.ch_dsn))["claimed"] == 0

    for store in ("cache", "cache_hot"):
        assert await harness.receipt_row_count(forgotten, store) == 1, store


@pytest.mark.asyncio
async def test_cache_ref_naming_another_tenant_is_refused_and_deletes_nothing(
    harness: Harness, object_store: FakeObjectStore
) -> None:
    """A cache locator is caller-written text; the tenant namespace decides.

    ``ibex_app`` holds INSERT on ``memory_artifact_refs``, so a crafted ref could
    name another tenant's object cache key. The stage refuses any key outside
    ``<row org>:{memory,hot_memories}:`` before it deletes anything — a permanent
    failure, because the locator cannot become valid on a retry — and the other
    tenant's cached copy must still exist afterwards.
    """
    other = await harness.seed()
    target = await harness.seed(with_refs=False)
    await harness.refs(
        RefSeed(
            org_id=target.org_id,
            memory_id=target.memory_id,
            session_id=None,
            locators={"cache": other.object_cache_key},
        )
    )
    await harness.queue(OutboxSeed.for_memory(target))

    out = await harness.run(ch_dsn=harness.env.ch_dsn)

    assert out["claimed"] == 1, out
    assert out["failed"] == 1, out
    assert out["partial"] == 0, out
    receipts = await harness.receipts(
        org_id=target.org_id, memory_id=target.memory_id
    )
    status, error, verified_at = receipts["cache"]
    assert status == "failed", receipts
    assert verified_at is None
    assert "tenant namespace" in (error or ""), error
    assert str(other.org_id) not in (error or ""), (
        "the refusal must not echo the locator it rejected"
    )
    assert harness.cached_object_present(other), (
        "the other tenant's cached memory object was deleted by a foreign ref"
    )
    assert (await harness.run(ch_dsn=harness.env.ch_dsn))["claimed"] == 0, (
        "a permanent locator failure must stop waking the row"
    )
