"""Memory-lifecycle erasure consumer: the paths where every store is proven.

Why this file exists: the forget path wrote a ``memory_lifecycle_outbox`` row and
nothing consumed it, so a forget could report success while the memory's
object-store capture, its ClickHouse evidence and the ``session_events`` row that
carried it still existed. These tests run the consumer end to end and assert the
rows are actually gone — not that a task returned a dict.

This module covers the happy path: every store verified, a redelivery that adds
nothing, and a memory with no copies. The failure, retry and tenant-isolation
paths are in ``test_memory_lifecycle_erasure_retry_postgres.py``; the seeding
harness, the object-store stub and the ClickHouse helper are shared from
``lifecycle_erasure_harness``, and the fixtures from ``conftest.py``.
"""

from __future__ import annotations

import pytest

from tests.integration.lifecycle_erasure_harness import (
    FakeObjectStore,
    Harness,
    OutboxSeed,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_consumer_verifies_every_store_and_deletes_the_copies(
    harness: Harness, object_store: FakeObjectStore
) -> None:
    forgotten, row_id = await harness.seed_queued(object_store)

    out = await harness.run(ch_dsn=harness.env.ch_dsn)

    assert out["claimed"] == 1, out
    assert out["complete"] == 1, out
    receipts = await harness.receipts(
        org_id=forgotten.org_id, memory_id=forgotten.memory_id
    )
    assert set(receipts) == {
        "objectstore",
        "clickhouse",
        "session_event",
        "cache",
        "cache_hot",
    }
    for store, (status, error, verified_at) in receipts.items():
        assert status == "verified", (store, error)
        assert error is None, (store, error)
        assert verified_at is not None, store

    state, delivered_at, _available, _attempts = await harness.outbox(row_id=row_id)
    assert state == "complete"
    assert delivered_at is not None

    assert object_store.deleted == [forgotten.object_uri]
    assert forgotten.object_uri not in object_store.present
    assert harness.clickhouse_count(forgotten) == 0, (
        "the ClickHouse evidence row must be gone, not merely marked"
    )
    assert await harness.session_event_count(forgotten) == 0, (
        "the session_events copy must be gone"
    )
    # The cache is the disclosure store: the content-bearing entry is gone, and
    # only this memory's member left the hot set — the other live member stays.
    assert not harness.cached_object_present(forgotten), (
        "the cached object still carries the forgotten memory's content"
    )
    assert not harness.hot_member_present(forgotten)
    assert harness.hot_other_member_present(forgotten), (
        "the hot set lost a live memory's score, not just the forgotten member"
    )
    # The refs stay: the receipt is the proof, the ref is the address it refers to.
    assert await harness.artifact_ref_count(forgotten) == 5


@pytest.mark.asyncio
async def test_redelivery_of_the_same_revision_writes_no_second_receipt(
    harness: Harness, object_store: FakeObjectStore
) -> None:
    forgotten, row_id = await harness.seed_queued(object_store)

    await harness.run(ch_dsn=harness.env.ch_dsn)
    first_receipts = await harness.receipts(
        org_id=forgotten.org_id, memory_id=forgotten.memory_id
    )
    _state, first_delivered, _available, _attempts = await harness.outbox(row_id=row_id)
    deleted_after_first = list(object_store.deleted)

    second = await harness.run(ch_dsn=harness.env.ch_dsn)

    assert second["claimed"] == 0, "a delivered row must not be claimed again"
    assert (
        await harness.receipts(
            org_id=forgotten.org_id, memory_id=forgotten.memory_id
        )
        == first_receipts
    ), "a redelivered revision must not rewrite its receipts"
    _state, second_delivered, _available, _attempts = await harness.outbox(row_id=row_id)
    assert second_delivered == first_delivered
    assert object_store.deleted == deleted_after_first


@pytest.mark.asyncio
async def test_memory_without_refs_is_not_applicable_not_failed(
    harness: Harness, object_store: FakeObjectStore
) -> None:
    forgotten = await harness.seed(with_refs=False)
    row_id = await harness.queue(OutboxSeed.for_memory(forgotten))

    out = await harness.run(ch_dsn=harness.env.ch_dsn)

    assert out["complete"] == 1, out
    receipts = await harness.receipts(
        org_id=forgotten.org_id, memory_id=forgotten.memory_id
    )
    # Only the stores whose producer records a ref for every copy get a receipt.
    # ClickHouse is not among them: "no ref" there means "not checked", so a
    # receipt would be a claim nobody made.
    assert set(receipts) == {"objectstore", "session_event", "cache", "cache_hot"}
    assert {status for status, _error, _at in receipts.values()} == {"not_applicable"}
    assert {verified_at for _status, _error, verified_at in receipts.values()} == {None}
    state, delivered_at, _available, _attempts = await harness.outbox(row_id=row_id)
    assert (state, delivered_at is not None) == ("complete", True)
    assert object_store.deleted == [], "no ref means no store call"
