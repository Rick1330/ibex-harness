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

import time

import pytest

from app.tasks import lifecycle_erasure
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
async def test_a_receipt_records_the_addresses_its_proof_covered(
    harness: Harness, object_store: FakeObjectStore
) -> None:
    """A proof is scoped to the locators it erased, not to the store.

    The receipt must name exactly the addresses this run staged, so a later copy
    at a new address is not mistaken for one already proved.
    """
    forgotten, _row_id = await harness.seed_queued(object_store)

    out = await harness.run(ch_dsn=harness.env.ch_dsn)

    assert out["complete"] == 1, out
    assert await harness.receipt_coverage(forgotten, "objectstore") == (
        forgotten.object_uri,
    )
    assert await harness.receipt_coverage(forgotten, "clickhouse") == (
        str(forgotten.ch_event_id),
    )
    assert await harness.receipt_coverage(forgotten, "session_event") == (
        str(forgotten.session_event_id),
    )
    assert await harness.receipt_coverage(forgotten, "cache") == (
        forgotten.object_cache_key,
    )
    assert await harness.receipt_coverage(forgotten, "cache_hot") == (
        forgotten.hot_cache_key,
    )


@pytest.mark.asyncio
async def test_a_slow_object_store_head_cannot_starve_the_cache_stores(
    harness: Harness,
    object_store: FakeObjectStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The archive re-check is bounded, so a slow store cannot eat the row's budget.

    The object store holds the memory's archive and answers the proof HEAD
    slowly. An expired check is "the object may be back", never "absent": the
    store is staged again, and the cache stores after it in the same row are
    still attempted and proved. Without the cap this run would sleep through the
    one-second HEAD before reaching any of them.
    """
    forgotten, _row_id = await harness.seed_queued(object_store)
    await harness.seed_receipt(
        forgotten,
        store="objectstore",
        covered_addresses=(forgotten.object_uri,),
    )
    object_store.delay = 1.0
    object_store.slow_calls = 1
    monkeypatch.setattr(lifecycle_erasure.sweep, "_PROOF_HEAD_CAP_SECONDS", 0.05)
    started = time.monotonic()

    out = await harness.run(ch_dsn=harness.env.ch_dsn)

    assert out["complete"] == 1, out
    assert object_store.deleted == [forgotten.object_uri], (
        "an expired proof must restage the store, not certify it"
    )
    receipts = await harness.receipts(
        org_id=forgotten.org_id, memory_id=forgotten.memory_id
    )
    assert receipts["cache"][0] == "verified", receipts
    assert receipts["cache_hot"][0] == "verified", receipts
    # The ClickHouse stage polls on a 0.5 s interval; the proof HEAD must not add
    # its full slow answer on top of that.
    assert time.monotonic() - started < 1.0, "the proof HEAD was not cut at its cap"


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
    # receipt would be a claim nobody made. The cache stores are different: their
    # keys are derivable from the row, so the consumer derives them and proves
    # them instead of reporting an absent ref as absence (A2).
    statuses = {store: status for store, (status, _error, _at) in receipts.items()}
    assert statuses == {
        "objectstore": "not_applicable",
        "session_event": "not_applicable",
        "cache": "verified",
        "cache_hot": "verified",
    }
    assert receipts["cache"][2] is not None, "a derived purge is stamped proved"
    assert receipts["cache_hot"][2] is not None
    state, delivered_at, _available, _attempts = await harness.outbox(row_id=row_id)
    assert (state, delivered_at is not None) == ("complete", True)
    assert object_store.deleted == [], "no ref means no store call"
