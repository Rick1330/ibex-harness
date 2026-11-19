"""Memory-lifecycle erasure of a ``purged`` row, after an organization deletion.

A ``purged`` row is the row whose hot cache address the consumer cannot derive:
the organization saga deletes the memory row before the sweep runs, so
``memories.agent_id`` — the only source of the per-agent hot key — is gone. The
saga now records that address in ``memory_artifact_refs`` in the same
transaction as the delete (000079), so the consumer stages it like any other
cache target: forgotten marker, ``ZREM``, verify absent.

Why the receipt alone is not enough: the saga's ``redis`` receipt proves the
org-wide delete *ran*. A create that committed before its ``refresh_hot`` can
land after that delete, and the receipt says nothing about the member after it.
The race test below places exactly that delayed write after the purge and before
the sweep; the fence test places it after the worker's first look and drives the
memory service's own guarded ``ZADD``, which the worker's marker must refuse.

A row queued by a saga that predates the ref insert has no address at all. It is
not completed on the receipt: ``not_applicable`` is read only when Redis is not
deployed, and a ``verified`` receipt is a delete that ran, not a member proved
absent.

The first case runs the real saga (``org_deletion._run_delete``) rather than
inserting a receipt by hand, so the evidence is produced by the code that will
produce it in production. The harness, object-store stub, and fixtures are shared
with the rest of the erasure suite.
"""

from __future__ import annotations

import ast
import pathlib
from collections.abc import Iterator
from dataclasses import replace
from uuid import uuid4

import pytest
import redis as redis_sync

from app.config import get_settings
from app.tasks import org_deletion
from tests.integration.lifecycle_erasure_harness import (
    FakeObjectStore,
    Forgotten,
    Harness,
    OutboxSeed,
    RefSeed,
    seed_cache_copies,
)
from tests.integration.tenant_pinning_support import sql_text

pytestmark = pytest.mark.integration

#: Stores the saga is told this deployment has. ClickHouse and the object store
#: are omitted deliberately: these cases are about the Redis verdict and the
#: worker's own proof, so a store the topology omits gets ``not_applicable``.
_DEPLOYED_STORES = "postgres,redis"

#: The memory service's hot-write script, read rather than copied: the fence only
#: works because the writer checks the marker in the same Redis script as ZADD.
_MEMORY_HOT_WRITE = (
    pathlib.Path(__file__).resolve().parents[4]
    / "services/memory/app/cache/hot_write.py"
)


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
    """Delete the memory row the way a pre-000079 org purge does."""
    async with harness.env.owner() as session, session.begin():
        await session.execute(
            sql_text(
                "DELETE FROM ibex_core.memories"
                " WHERE org_id = :org AND id = :memory"
            ),
            {"org": forgotten.org_id, "memory": forgotten.memory_id},
        )


async def _redis_receipt(harness: Harness, forgotten: Forgotten) -> str | None:
    """The organization deletion's latest Redis verdict for this org."""
    async with harness.env.owner() as session:
        row = (
            await session.execute(
                sql_text(
                    """
                    SELECT receipt.status
                      FROM ibex_core.deletion_store_receipts AS receipt
                      JOIN ibex_core.org_deletion_jobs AS job
                        ON job.id = receipt.job_id
                     WHERE job.org_id = :org AND receipt.store = 'redis'
                     ORDER BY (receipt.status = 'verified') DESC,
                              receipt.updated_at DESC
                     LIMIT 1
                    """
                ),
                {"org": forgotten.org_id},
            )
        ).first()
    return str(row[0]) if row is not None else None


async def _seed_redis_receipt(
    harness: Harness, forgotten: Forgotten, status: str
) -> None:
    """Write the receipt a pre-000079 saga would have left behind."""
    job_id = await _seed_job(harness, forgotten)
    async with harness.env.owner() as session, session.begin():
        await session.execute(
            sql_text(
                """
                INSERT INTO ibex_core.deletion_store_receipts (
                    job_id, store, scope, status, verified_absent_at, idempotency_key
                ) VALUES (
                    :job, 'redis', 'org', :status,
                    CASE WHEN :status = 'verified' THEN NOW() ELSE NULL END,
                    :idem
                )
                """
            ),
            {"job": job_id, "status": status, "idem": f"{job_id}:redis:org"},
        )


def _hot_guard_script() -> str:
    """The memory service's guarded hot ZADD, read from its own source."""
    module = ast.parse(_MEMORY_HOT_WRITE.read_text(encoding="utf-8"))
    for node in module.body:
        for target in getattr(node, "targets", ()):
            if isinstance(target, ast.Name) and target.id == "_HOT_ZADD_TRIM_LUA":
                return ast.literal_eval(node.value)
    raise AssertionError("the memory service's hot guard script moved")


def _guarded_hot_write(harness: Harness, forgotten: Forgotten) -> int:
    """Attempt the delayed ``refresh_hot`` through the memory service's guard.

    The script refuses (returns 0) while the memory's forgotten marker exists.
    Driving the real script is what makes this evidence about the two services
    agreeing on the fence, not about a test-local imitation of it.
    """
    client = redis_sync.Redis.from_url(harness.env.redis_url, decode_responses=True)
    try:
        return int(
            client.register_script(_hot_guard_script())(
                keys=[
                    forgotten.hot_cache_key,
                    harness.forgotten_marker_key(forgotten),
                ],
                args=[1.0, str(forgotten.memory_id), 3600],
            )
        )
    finally:
        client.close()


@pytest.mark.asyncio
async def test_a_delayed_hot_write_after_the_org_purge_is_removed_before_complete(
    harness: Harness,
    purge_deployed_stores: object,
) -> None:
    """The receipt cannot settle the row once a delayed write lands after it.

    The saga deletes every hot key and records a verified receipt. A create that
    committed before its ``refresh_hot`` then lands its member: after the delete,
    before the sweep. The saga recorded the address before it deleted the memory,
    so the sweep stages it — marker, ZREM, verify — and only then completes.
    The member is absent, and the row was never ``complete`` while it survived.
    """
    del purge_deployed_stores
    forgotten = await harness.seed(with_refs=False)
    forgotten = await _seed_copies_without_refs(harness, forgotten)

    outcome = await _run_saga(harness, forgotten)
    assert outcome["status"] == "succeeded", outcome
    assert not harness.hot_member_present(forgotten)
    assert await harness.artifact_refs(forgotten) == {
        "cache_hot": (forgotten.hot_cache_key,)
    }, "the saga must record the address before it deletes the memory"
    assert await _redis_receipt(harness, forgotten) == "verified"

    harness.add_hot_member(forgotten)  # the delayed refresh_hot lands
    assert harness.hot_member_present(forgotten), "fixture precondition: the race is set"

    row_id = await _purged_row_id(harness, forgotten)
    sweep = await harness.run(ch_dsn=None)

    assert sweep["claimed"] == 1, sweep
    assert sweep["complete"] == 1, sweep
    assert not harness.hot_member_present(forgotten)
    receipts = await harness.receipts(
        org_id=forgotten.org_id, memory_id=forgotten.memory_id
    )
    assert receipts["cache_hot"][0] == "verified", receipts
    assert receipts["cache_hot"][2] is not None, "a verified receipt carries its timestamp"
    state, delivered_at, _available, attempts = await harness.outbox(row_id=row_id)
    assert (state, delivered_at is not None, attempts) == ("complete", True, 1)


@pytest.mark.asyncio
async def test_a_hot_write_after_the_workers_first_look_is_fenced(
    harness: Harness,
    object_store: FakeObjectStore,
    purge_deployed_stores: object,
) -> None:
    """The marker the first run writes is what stops the delayed write.

    The first sweep cannot settle the row because the object store refuses, but
    it has already staged the hot store and written the marker. The delayed
    ``refresh_hot`` is then attempted through the memory service's own guarded
    ZADD and is refused. The retry completes with the member still absent.
    """
    del purge_deployed_stores
    forgotten = await harness.seed(with_refs=False)
    forgotten = await _seed_copies_without_refs(harness, forgotten)
    await harness.refs(
        RefSeed(
            org_id=forgotten.org_id,
            memory_id=forgotten.memory_id,
            session_id=None,
            locators={"objectstore": forgotten.object_uri},
        )
    )
    object_store.present.add(forgotten.object_uri)
    object_store.raises = True

    outcome = await _run_saga(harness, forgotten)
    assert outcome["status"] == "succeeded", outcome

    row_id = await _purged_row_id(harness, forgotten)
    first = await harness.run(ch_dsn=None)
    assert first["partial"] == 1, first
    assert harness.forgotten_marker_present(forgotten), (
        "the first look must leave the fence behind"
    )

    assert _guarded_hot_write(harness, forgotten) == 0, (
        "the marker must refuse the delayed write"
    )
    assert not harness.hot_member_present(forgotten)

    object_store.raises = False
    await harness.make_due(row_id)
    second = await harness.run(ch_dsn=None)

    assert second["complete"] == 1, second
    assert not harness.hot_member_present(forgotten)
    state, delivered_at, _available, _attempts = await harness.outbox(row_id=row_id)
    assert (state, delivered_at is not None) == ("complete", True)


@pytest.mark.asyncio
@pytest.mark.parametrize("receipt_status", ["verified", None])
async def test_a_purged_row_without_an_address_is_never_completed_on_the_receipt(
    harness: Harness,
    receipt_status: str | None,
) -> None:
    """A row from a saga that recorded no address fails; it does not borrow one.

    The receipt says the org-wide delete ran. It cannot say that a delayed write
    did not follow it, so neither a ``verified`` receipt nor the absence of one
    settles the hot store. The row records the failure and stops waking.
    """
    forgotten = await harness.seed(with_refs=False)
    await _delete_memory(harness, forgotten)
    if receipt_status is not None:
        await _seed_redis_receipt(harness, forgotten, receipt_status)
    row_id = await harness.queue(OutboxSeed.for_memory(forgotten, event_type="purged"))

    sweep = await harness.run(ch_dsn=None)

    assert sweep["claimed"] == 1, sweep
    assert sweep["failed"] == 1, sweep
    receipts = await harness.receipts(
        org_id=forgotten.org_id, memory_id=forgotten.memory_id
    )
    status, error, verified_at = receipts["cache_hot"]
    assert (status, verified_at) == ("failed", None), receipts
    assert "not a fence" in (error or ""), error
    state, delivered_at, _available, _attempts = await harness.outbox(row_id=row_id)
    assert (state, delivered_at) == ("failed", None)
