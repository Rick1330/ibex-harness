"""Memory-lifecycle erasure consumer: the paths where a store cannot be proven.

Why this module is separate: these are the cases where the honest answer is
"not yet" or "refused", and each of them has a way to be wrong that the happy
path cannot show. An unreachable store must be ``failed`` — never ``verified``
and never ``not_applicable``. A superseded revision is retired with the newer
row's state instead of inventing one. A locator naming another tenant is refused
without echoing it. The happy path is in
``test_memory_lifecycle_erasure_postgres.py``; the harness is shared from
``lifecycle_erasure_harness``, and the fixtures come from ``conftest.py``.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import pytest

from app import objectstore_client
from app.tasks import lifecycle_erasure
from tests.integration.lifecycle_erasure_harness import (
    FakeObjectStore,
    Forgotten,
    Harness,
    OutboxSeed,
    RefSeed,
    seed_clickhouse_event,
)

pytestmark = pytest.mark.integration


async def _require_unreachable_clickhouse_is_failed(
    harness: Harness, forgotten: Forgotten, row_id: str
) -> None:
    """First run: ClickHouse is deployed but unconfigured, so its receipt fails.

    ``not_applicable`` would mean "this memory has no ClickHouse copy", which is
    false — the memory has one and it is still there. ``verified`` would be a lie
    with a timestamp on it.
    """
    first = await harness.run(ch_dsn=None)

    assert first["claimed"] == 1, first
    assert first["partial"] == 1, first
    receipts = await harness.receipts(
        org_id=forgotten.org_id, memory_id=forgotten.memory_id
    )
    clickhouse = receipts["clickhouse"]
    assert clickhouse[0] == "failed", clickhouse
    assert clickhouse[2] is None, "a failed receipt must not carry a verified timestamp"
    assert "clickhouse" in (clickhouse[1] or "").lower(), clickhouse
    assert receipts["objectstore"][0] == "verified"
    assert receipts["session_event"][0] == "verified"

    state, delivered_at, available_at, attempts = await harness.outbox(row_id=row_id)
    assert state == "partial"
    assert delivered_at is None, "a partial erasure is not delivered"
    assert attempts == 1
    assert available_at > datetime.now(tz=UTC), "the retry must be scheduled in the future"
    assert harness.clickhouse_count(forgotten) == 1, (
        "the unreachable store still holds the copy"
    )


async def _require_retry_completes(
    harness: Harness, forgotten: Forgotten, row_id: str
) -> None:
    """Second run, with the backoff fast-forwarded: the retry completes."""
    await harness.make_due(row_id)

    second = await harness.run(ch_dsn=harness.env.ch_dsn)

    assert second["complete"] == 1, second
    receipts = await harness.receipts(
        org_id=forgotten.org_id, memory_id=forgotten.memory_id
    )
    assert {status for status, _error, _at in receipts.values()} == {"verified"}
    assert receipts["clickhouse"][2] is not None
    state, delivered_at, _available, attempts = await harness.outbox(row_id=row_id)
    assert (state, delivered_at is not None, attempts) == ("complete", True, 2)


@pytest.mark.asyncio
async def test_unreachable_store_leaves_partial_then_a_retry_completes(
    harness: Harness, object_store: FakeObjectStore
) -> None:
    forgotten, row_id = await harness.seed_queued(object_store)

    await _require_unreachable_clickhouse_is_failed(harness, forgotten, row_id)
    await _require_retry_completes(harness, forgotten, row_id)

    assert object_store.deleted == [forgotten.object_uri], (
        "a store already verified must not be staged again on the retry"
    )
    assert harness.clickhouse_count(forgotten) == 0


@pytest.mark.asyncio
async def test_a_copy_recorded_between_two_sweeps_is_erased_by_the_second(
    harness: Harness, object_store: FakeObjectStore
) -> None:
    """A receipt proves addresses, not a store, so a between-sweeps copy is staged.

    First sweep: the object store fails transiently, so the row stays ``partial``
    while the session-event copy at the recorded address is verified. A producer
    then records a second session-event copy for the same memory and revision —
    an address the earlier receipt never covered. Settling on that receipt would
    leave the copy alive and mark the row complete; the retry must stage the store
    again and erase it.
    """
    forgotten, row_id = await harness.seed_queued(object_store)
    object_store.raises = True

    first = await harness.run(ch_dsn=harness.env.ch_dsn)

    assert first["partial"] == 1, first
    assert await harness.receipt_coverage(forgotten, "session_event") == (
        str(forgotten.session_event_id),
    ), "the first sweep proves only the address it saw"

    late_event_id = await harness.add_session_event_copy(forgotten)
    assert (
        await harness.session_event_by_id_count(
            org_id=forgotten.org_id, event_id=late_event_id
        )
        == 1
    )

    object_store.raises = False
    await harness.make_due(row_id)

    second = await harness.run(ch_dsn=harness.env.ch_dsn)

    assert second["complete"] == 1, second
    assert (
        await harness.session_event_by_id_count(
            org_id=forgotten.org_id, event_id=late_event_id
        )
        == 0
    ), "the copy recorded between sweeps must be erased, not settled over"
    coverage = await harness.receipt_coverage(forgotten, "session_event")
    assert set(coverage or ()) == {
        str(forgotten.session_event_id),
        str(late_event_id),
    }, "the replacement receipt covers every address it staged"
    state, delivered_at, _available, attempts = await harness.outbox(row_id=row_id)
    assert (state, delivered_at is not None, attempts) == ("complete", True, 2)


@pytest.mark.asyncio
async def test_a_reappeared_object_is_deleted_again_on_the_retry(
    harness: Harness, object_store: FakeObjectStore
) -> None:
    """A stored ``verified`` receipt does not cover an object that came back.

    First run: ClickHouse is unreachable, so the row stays ``partial`` while the
    object store is already proven. The archive is then re-created at the same
    locator — the key is derived from the row and nothing fences a re-archive —
    and the retry has to delete it again. Trusting the earlier receipt would leave
    the object in place and retry forever against a proof that no longer holds.
    """
    forgotten, row_id = await harness.seed_queued(object_store)

    first = await harness.run(ch_dsn=None)
    assert first["partial"] == 1, first
    assert object_store.deleted == [forgotten.object_uri]

    object_store.present.add(forgotten.object_uri)
    await harness.make_due(row_id)

    second = await harness.run(ch_dsn=harness.env.ch_dsn)

    assert second["complete"] == 1, second
    assert object_store.deleted == [forgotten.object_uri, forgotten.object_uri], (
        "the reappeared object must be deleted again, not certified by the old receipt"
    )
    assert object_store.present == set()
    receipts = await harness.receipts(
        org_id=forgotten.org_id, memory_id=forgotten.memory_id
    )
    assert receipts["objectstore"][0] == "verified", receipts
    state, delivered_at, _available, attempts = await harness.outbox(row_id=row_id)
    assert (state, delivered_at is not None, attempts) == ("complete", True, 2)


@pytest.mark.asyncio
async def test_a_failed_redelete_replaces_the_verified_receipt(
    harness: Harness, object_store: FakeObjectStore
) -> None:
    """A proof that a live copy contradicted must not outlive the failure.

    First run proves the archive absent. The archive then reappears and the
    re-delete fails, so the receipt has to say ``failed`` with a reason and no
    timestamp: keeping ``verified`` would describe a store that holds a live
    copy. A later retry deletes it and earns a fresh proof.
    """
    forgotten, row_id = await harness.seed_queued(object_store)

    first = await harness.run(ch_dsn=None)
    assert first["partial"] == 1, first
    proved_at = (
        await harness.receipts(org_id=forgotten.org_id, memory_id=forgotten.memory_id)
    )["objectstore"][2]
    assert proved_at is not None

    object_store.present.add(forgotten.object_uri)
    object_store.delete_failures = 1
    await harness.make_due(row_id)

    second = await harness.run(ch_dsn=None)

    assert second["partial"] == 1, second
    status, error, verified_at = (
        await harness.receipts(org_id=forgotten.org_id, memory_id=forgotten.memory_id)
    )["objectstore"]
    assert status == "failed"
    assert verified_at is None, "a failed receipt must clear the verified timestamp"
    assert "503" in (error or ""), error
    state, delivered_at, _available, attempts = await harness.outbox(row_id=row_id)
    assert (state, delivered_at, attempts) == ("partial", None, 2)

    await harness.make_due(row_id)
    third = await harness.run(ch_dsn=harness.env.ch_dsn)

    assert third["complete"] == 1, third
    status, error, verified_at = (
        await harness.receipts(org_id=forgotten.org_id, memory_id=forgotten.memory_id)
    )["objectstore"]
    assert (status, error) == ("verified", None)
    assert verified_at is not None and verified_at > proved_at, (
        "the proof that replaced the failure must carry a fresh timestamp"
    )


@pytest.mark.asyncio
async def test_an_unanswerable_recheck_keeps_the_valid_verified_receipt(
    harness: Harness, object_store: FakeObjectStore
) -> None:
    """A transient outage must not cost the store a proof it already earned.

    The HEAD cannot answer and the re-delete fails for the same reason, so this
    run has no evidence the object came back. The stored ``verified`` receipt and
    its timestamp must survive; the row is ``partial`` and retries.
    """
    forgotten, row_id = await harness.seed_queued(object_store)
    await harness.seed_receipt(
        forgotten,
        store="objectstore",
        covered_addresses=(forgotten.object_uri,),
    )
    proved_at = (
        await harness.receipts(org_id=forgotten.org_id, memory_id=forgotten.memory_id)
    )["objectstore"][2]
    assert proved_at is not None

    object_store.raises = True
    await harness.make_due(row_id)

    out = await harness.run(ch_dsn=None)

    assert out["partial"] == 1, out
    status, _error, verified_at = (
        await harness.receipts(org_id=forgotten.org_id, memory_id=forgotten.memory_id)
    )["objectstore"]
    assert status == "verified"
    assert verified_at == proved_at, "an unanswered recheck must not refresh or drop it"
    assert object_store.deleted == []
    state, delivered_at, _available, _attempts = await harness.outbox(row_id=row_id)
    assert (state, delivered_at) == ("partial", None)


async def _erase_stale_claim(harness: Harness, forgotten: Forgotten) -> str:
    """Claim revision 2, deliver revision 3, then erase the stale claim.

    This is the interleaving the retirement path exists for: revision 2 is
    claimed, revision 3 is delivered by another worker, and then revision 2 runs.
    """
    settings = harness.settings(ch_dsn=harness.env.ch_dsn)
    async with harness.factory(ch_dsn=harness.env.ch_dsn) as factory:
        claimed = await lifecycle_erasure._claim_one(factory, settings)
        assert claimed is not None and claimed.revision == 2
        await harness.queue(
            OutboxSeed.for_memory(
                forgotten,
                revision=3,
                event_type="purged",
                delivered=True,
                erasure_state="complete",
            )
        )
        return await lifecycle_erasure._erase_row(
            factory, settings, claimed, time.monotonic() + 60.0
        )


@pytest.mark.asyncio
async def test_superseded_revision_is_retired_with_the_newer_state(
    harness: Harness, object_store: FakeObjectStore
) -> None:
    """A row older than a delivered one has nothing left to prove.

    Erasing again would be harmless but would write receipts for a revision whose
    proof is already superseded, so the row is retired and copies revision 3's
    state.
    """
    forgotten = await harness.seed()
    stale_id = await harness.queue(OutboxSeed.for_memory(forgotten, revision=2))

    outcome = await _erase_stale_claim(harness, forgotten)

    assert outcome == "retired", outcome
    state, delivered_at, _available, _attempts = await harness.outbox(row_id=stale_id)
    assert (state, delivered_at is not None) == ("complete", True)
    assert (
        await harness.receipts(
            org_id=forgotten.org_id, memory_id=forgotten.memory_id
        )
        == {}
    ), "a retired row proves nothing and must write no receipt"
    assert object_store.deleted == []
    # A later sweep has nothing to do: the row is delivered and the newer one too.
    assert (await harness.run(ch_dsn=harness.env.ch_dsn))["claimed"] == 0


@pytest.mark.asyncio
async def test_erasure_of_one_tenant_leaves_another_tenants_copies_alone(
    harness: Harness, object_store: FakeObjectStore
) -> None:
    """Only org A's row is queued; org B's event with the same kind of locator stays.

    The consumer deletes by ``(org_id, id)`` under ``ibex_app`` plus the org GUC,
    so a missing or wrong GUC would surface here as a cross-tenant deletion.
    """
    forgotten = await harness.seed()
    other = await harness.seed()
    await harness.queue(OutboxSeed.for_memory(forgotten))
    object_store.present.update({forgotten.object_uri, other.object_uri})

    await harness.run(ch_dsn=harness.env.ch_dsn)

    assert await harness.session_event_count(other) == 1, (
        "another tenant's session event must survive"
    )
    assert object_store.deleted == [forgotten.object_uri]
    assert harness.clickhouse_count(other) == 1
    assert harness.cached_object_present(other), (
        "another tenant's cached memory object must survive"
    )
    assert harness.hot_member_present(other)
    assert not harness.cached_object_present(forgotten)
    assert (
        await harness.receipts(org_id=other.org_id, memory_id=other.memory_id) == {}
    )


@pytest.mark.asyncio
async def test_clickhouse_evidence_without_a_ref_is_unproven_not_not_applicable(
    harness: Harness, object_store: FakeObjectStore
) -> None:
    """No producer records a per-memory ClickHouse locator, so no claim is made.

    The failure this pins: a memory with ClickHouse evidence but no ``clickhouse``
    ref used to receive ``not_applicable`` for that store — a receipt that says
    "the memory has no copy here" while the row is still in ``ibex.evidence_events``.
    The consumer now makes no ClickHouse claim at all, which is the honest answer;
    a ref that *does* name ClickHouse is erased and receipted (the happy path).
    """
    forgotten = await harness.seed(with_refs=False)
    # The evidence exists in ClickHouse exactly as a producer would have written it.
    seed_clickhouse_event(
        harness.env.ch_dsn, org_id=forgotten.org_id, event_id=forgotten.ch_event_id
    )
    await harness.queue(OutboxSeed.for_memory(forgotten))

    out = await harness.run(ch_dsn=harness.env.ch_dsn)

    assert out["claimed"] == 1, out
    receipts = await harness.receipts(
        org_id=forgotten.org_id, memory_id=forgotten.memory_id
    )
    assert "clickhouse" not in receipts, (
        "a store with no provenance producer must not be receipted at all"
    )
    assert set(receipts) == {"objectstore", "session_event", "cache", "cache_hot"}
    assert harness.clickhouse_count(forgotten) == 1, (
        "the unproven store is not claimed as erased; the row is the open gap"
    )


class _Head404:
    """The one httpx.Response attribute ``object_exists`` reads."""

    status_code = 404


def _stub_s3(
    monkeypatch: pytest.MonkeyPatch, cross_uri: str
) -> tuple[list[str], set[str]]:
    """Stub only the S3 wire calls; the tenant-prefix guard stays under test."""
    deleted: list[str] = []
    present = {cross_uri}

    def _delete(cfg: Any, key: str) -> None:
        deleted.append(key)
        present.discard(f"s3://{cfg.bucket}/{key}")

    monkeypatch.setattr(objectstore_client, "_delete_key", _delete)
    monkeypatch.setattr(
        objectstore_client, "_sign_and_request", lambda _req: _Head404()
    )
    return deleted, present


@pytest.mark.asyncio
async def test_objectstore_ref_naming_another_tenant_fails_and_deletes_nothing(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``locator`` is caller-written text, so the org prefix decides ownership.

    The ``object_store`` fixture is deliberately not used here: the real
    ``delete_uri``/``object_exists`` run so the tenant-prefix guard is the code
    under test. Only the S3 wire call is stubbed, which also makes the assertion
    sharp — a guard that let the locator through would reach ``_delete_key`` and
    remove another org's object.
    """
    other = await harness.seed()
    target = await harness.seed(with_refs=False)
    cross_uri = (
        f"s3://ibex-sessions/{other.org_id}/capture/full/{other.ch_event_id}.json"
    )
    await harness.refs(
        RefSeed(
            org_id=target.org_id,
            memory_id=target.memory_id,
            session_id=None,
            locators={"objectstore": cross_uri},
        )
    )
    await harness.queue(OutboxSeed.for_memory(target))
    deleted, present = _stub_s3(monkeypatch, cross_uri)

    out = await harness.run(ch_dsn=harness.env.ch_dsn)

    assert out["claimed"] == 1, out
    # A cross-tenant locator is a permanent validation failure: it cannot become
    # valid on the next sweep, so the row is terminally failed rather than partial.
    assert out["failed"] == 1, out
    assert out["partial"] == 0, out
    receipts = await harness.receipts(
        org_id=target.org_id, memory_id=target.memory_id
    )
    status, error, verified_at = receipts["objectstore"]
    assert status == "failed", receipts
    assert verified_at is None
    assert "tenant prefix" in (error or ""), error
    assert str(other.org_id) not in (error or ""), (
        "the refusal must not echo the locator it rejected"
    )
    assert deleted == [], "no key was deleted for the rejected locator"
    assert cross_uri in present, "the other tenant's object is untouched"
    assert harness.clickhouse_count(other) == 1
    # No second attempt: the terminal failed row is no longer claimable.
    assert (await harness.run(ch_dsn=harness.env.ch_dsn))["claimed"] == 0
