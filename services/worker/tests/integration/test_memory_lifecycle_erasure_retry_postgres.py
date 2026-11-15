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
    assert set(receipts) == {"objectstore", "session_event"}
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
    assert out["partial"] == 1, out
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
