"""Memory-lifecycle erasure of a ``purged`` row, after an organization deletion.

A ``purged`` row is the one row whose hot cache address this consumer cannot
derive: the organization saga deletes the memory row before the sweep runs, so
``memories.agent_id`` — the only source of the per-agent hot key — is gone. This
module proves the two halves of the honest answer:

* the row settles on the saga's own evidence. The org-wide Redis stage removes
  every ``{org}:hot_memories:*`` key and records a ``redis`` receipt, so a
  ``verified`` receipt is proof the member is gone even though its key can no
  longer be computed;
* without that receipt the row retries. It is never ``verified`` and never
  ``not_applicable``, because neither this consumer nor the saga has looked.

The first case runs the real saga (``org_deletion._run_delete``) rather than
inserting a receipt by hand, so the evidence is produced by the code that will
produce it in production. The harness, object-store stub, and fixtures are shared
with the rest of the erasure suite.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from uuid import uuid4

import pytest

from app.config import get_settings
from app.tasks import org_deletion
from tests.integration.lifecycle_erasure_harness import (
    FakeObjectStore,
    Forgotten,
    Harness,
    OutboxSeed,
    seed_cache_copies,
)
from tests.integration.tenant_pinning_support import sql_text

pytestmark = pytest.mark.integration

#: Stores the saga is told this deployment has. ClickHouse and the object store
#: are omitted deliberately: this case is about the Redis verdict, and a store
#: the topology omits gets ``not_applicable`` instead of an unreachable failure.
_DEPLOYED_STORES = "postgres,redis"


@pytest.fixture
def purge_deployed_stores(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Make ``get_settings()`` describe a Postgres + Redis deletion topology.

    ``org_deletion._run_delete`` reads the process settings, and the suite's
    ``integration_settings`` fixture has already cached them, so the cache is
    cleared on both sides of the test. The DSN and Redis URL come from the
    environment that fixture set.
    """
    monkeypatch.setenv("IBEX_ORG_DELETION_DEPLOYED_STORES", _DEPLOYED_STORES)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _seed_job(harness: Harness, forgotten: Forgotten) -> str:
    """Add the pending deletion job the API would have created for this org."""
    job_id = uuid4()
    async with harness.env.owner() as session, session.begin():
        await session.execute(
            sql_text(
                "INSERT INTO ibex_core.org_deletion_jobs (id, org_id, status)"
                " VALUES (:id, :org, 'pending')"
            ),
            {"id": job_id, "org": forgotten.org_id},
        )
    return str(job_id)


async def _run_saga(harness: Harness, forgotten: Forgotten) -> dict[str, str]:
    """Run the real organization-deletion saga for the seeded org."""
    job_id = await _seed_job(harness, forgotten)
    return await org_deletion._run_delete(job_id=job_id, org_id=str(forgotten.org_id))


async def _purged_row_id(harness: Harness, forgotten: Forgotten) -> str:
    """The outbox row the saga's memory delete inserted."""
    async with harness.env.owner() as session:
        row = (
            await session.execute(
                sql_text(
                    "SELECT id::text FROM ibex_core.memory_lifecycle_outbox"
                    " WHERE org_id = :org AND memory_id = :memory"
                    " AND event_type = 'purged'"
                ),
                {"org": forgotten.org_id, "memory": forgotten.memory_id},
            )
        ).first()
    assert row is not None, "the org purge must emit a purged lifecycle event"
    return str(row[0])


async def _seed_copies_without_refs(
    harness: Harness, forgotten: Forgotten
) -> Forgotten:
    """Seed the cache copies a pre-000078 write left behind, with no refs.

    This is the row that exposed the defect: the copies exist, nothing recorded
    their addresses, and the org purge deletes the memory row the hot key would
    have been derived from.
    """
    object_key, hot_key = seed_cache_copies(
        harness.env.redis_url,
        org_id=forgotten.org_id,
        agent_id=forgotten.agent_id,
        memory_id=forgotten.memory_id,
    )
    return replace(forgotten, object_cache_key=object_key, hot_cache_key=hot_key)


async def _delete_memory(harness: Harness, forgotten: Forgotten) -> None:
    """Delete the memory row the way the org purge does, leaving its outbox row."""
    async with harness.env.owner() as session, session.begin():
        await session.execute(
            sql_text(
                "DELETE FROM ibex_core.memories"
                " WHERE org_id = :org AND id = :memory"
            ),
            {"org": forgotten.org_id, "memory": forgotten.memory_id},
        )


@pytest.mark.asyncio
async def test_org_deletion_settles_the_purged_rows_hot_store_from_its_own_receipt(
    harness: Harness,
    purge_deployed_stores: object,
) -> None:
    """The org purge's ``verified`` Redis receipt is the hot store's proof.

    Before the fix the row failed permanently: the hot key needs the memory's
    agent, the saga had deleted the memory row, and an underivable address was
    read as a dead end. The org-wide purge is not a dead end — it deleted the
    member — so the row completes on that evidence.
    """
    del purge_deployed_stores
    forgotten = await harness.seed(with_refs=False)
    forgotten = await _seed_copies_without_refs(harness, forgotten)
    assert harness.hot_member_present(forgotten), "fixture precondition: the member exists"

    outcome = await _run_saga(harness, forgotten)
    assert outcome["status"] == "succeeded", outcome
    assert not harness.hot_member_present(forgotten), (
        "the org-wide Redis stage is what makes the receipt evidence"
    )

    row_id = await _purged_row_id(harness, forgotten)
    sweep = await harness.run(ch_dsn=None)

    assert sweep["claimed"] == 1, sweep
    assert sweep["complete"] == 1, sweep
    receipts = await harness.receipts(
        org_id=forgotten.org_id, memory_id=forgotten.memory_id
    )
    assert receipts["cache_hot"][0] == "verified", receipts
    assert receipts["cache_hot"][2] is not None, "a verified receipt carries its timestamp"
    assert receipts["cache"][0] == "verified", receipts
    state, delivered_at, _available, attempts = await harness.outbox(row_id=row_id)
    assert (state, delivered_at is not None, attempts) == ("complete", True, 1)


@pytest.mark.asyncio
async def test_purged_row_without_a_purge_receipt_retries_and_claims_nothing(
    harness: Harness,
    object_store: FakeObjectStore,
) -> None:
    """No receipt yet is "not proven", not "nothing to erase" and not "done".

    The saga writes its Redis receipt in a later transaction than the ``purged``
    row, so a sweep can claim the row first. That run must schedule a retry: an
    underivable key with no org verdict is exactly the state in which neither
    this consumer nor the saga has looked at the hot set.
    """
    forgotten = await harness.seed(with_refs=False)
    await _delete_memory(harness, forgotten)
    row_id = await harness.queue(OutboxSeed.for_memory(forgotten, event_type="purged"))

    sweep = await harness.run(ch_dsn=None)

    assert sweep["claimed"] == 1, sweep
    assert sweep["partial"] == 1, sweep
    receipts = await harness.receipts(
        org_id=forgotten.org_id, memory_id=forgotten.memory_id
    )
    status, error, verified_at = receipts["cache_hot"]
    assert status == "failed", receipts
    assert verified_at is None, "an unproven store must not carry a verified timestamp"
    assert "organization purge" in (error or ""), error
    state, delivered_at, _available, attempts = await harness.outbox(row_id=row_id)
    assert (state, delivered_at, attempts) == ("partial", None, 1)
    assert object_store.deleted == [], "no store was staged on this row"
