"""A committed forget must record its cache eviction, not log it and move on.

Why this file exists: ``invalidate_forgotten_memory`` used to call the cache
writer, catch its exception and log a warning. Two failures compounded there: the
writer itself swallowed ``RedisError`` and returned, so the caller could not even
observe the failure, and nothing durable said the forgotten memory's content might
still be served from Redis for up to ``memory_cache_ttl_seconds``.

The contract asserted here, and the authority boundary behind it:

* the request path retries a failed eviction and, on exhaustion, records the
  attempt as ``failed`` on the outbox row — the erasure ledger sees outstanding
  work, not a clean bill of health;
* a later success clears the attempt back to ``pending``;
* **receipts are worker-only** (000075 revoked receipt writes from the tenant), so
  this path writes no proof. A worker receipt always wins over the attempt column:
  ``verified`` is reported even if the request path recorded a failure;
* no cache configured records no attempt and writes no ref — the worker then
  answers ``not_applicable`` from the absent refs;
* a cache store with neither receipt nor failed attempt is ``pending``, never
  ``verified``.

PostgreSQL is real, so the outbox columns, refs and receipts are exercised
through RLS as the tenant. Redis is not needed here: the worker suite runs the
consumer against a real Redis and proves the keys are gone. The writer is a stub
because the subject is the ledger discipline, not the Redis wire.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cache.memory_keys import HOT_CACHE_STORE, OBJECT_CACHE_STORE
from app.routers.memories import ForgetMemoryContext, forget_memory
from app.routers.memory_forget_support import (
    ERASURE_STORES,
    invalidate_forgotten_memory,
    read_forget_erasure,
)
from app.schemas.memories import ForgetMemoryRequest
from tests.integration import lifecycle_erasure_support
from tests.integration.conftest import seed_org_agent_memory

pytestmark = pytest.mark.integration

_execute_sql = lifecycle_erasure_support.execute_sql
_fetch_rows = lifecycle_erasure_support.fetch_rows


class _CacheWriter:
    """A cache writer that fails a fixed number of times before succeeding."""

    def __init__(self, *, failures: int = 0) -> None:
        self.failures = failures
        self.calls = 0

    def object_key(self, org_id: UUID, memory_id: UUID) -> str:
        return f"{org_id}:memory:{memory_id}"

    def hot_key(self, org_id: UUID, agent_id: UUID) -> str:
        return f"{org_id}:hot_memories:{agent_id}"

    async def forget_memory(self, *, org_id: UUID, agent_id: UUID, memory_id: UUID) -> None:
        del org_id, agent_id, memory_id
        self.calls += 1
        if self.calls <= self.failures:
            raise OSError("redis is unreachable")


async def _forget(
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id: UUID,
    agent_id: UUID,
    memory_id: UUID,
    cache_writer: _CacheWriter | None,
):
    ctx = ForgetMemoryContext(
        token=SimpleNamespace(org_id=org_id, agent_id=agent_id),
        session_factory=factory,
        cache_writer=cache_writer,
    )
    return await forget_memory(memory_id, ForgetMemoryRequest(expected_revision=1), ctx)


async def _attempt(
    factory: async_sessionmaker[AsyncSession], *, org_id: UUID, memory_id: UUID
) -> tuple[str, str | None]:
    rows = await _fetch_rows(
        factory,
        org_id,
        """
        SELECT cache_eviction_state, cache_eviction_error
          FROM ibex_core.memory_lifecycle_outbox
         WHERE org_id = :org AND memory_id = :memory
         ORDER BY revision DESC
         LIMIT 1
        """,
        {"org": org_id, "memory": memory_id},
    )
    return str(rows[0][0]), rows[0][1]


async def _cache_ref_count(
    factory: async_sessionmaker[AsyncSession], *, org_id: UUID, memory_id: UUID
) -> int:
    rows = await _fetch_rows(
        factory,
        org_id,
        """
        SELECT count(*)
          FROM ibex_core.memory_artifact_refs
         WHERE org_id = :org AND memory_id = :memory AND store IN ('cache','cache_hot')
        """,
        {"org": org_id, "memory": memory_id},
    )
    return int(rows[0][0])


async def _seed_worker_receipt(
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id: UUID,
    memory_id: UUID,
    revision: int,
    store: str,
    status: str,
) -> None:
    """Write the receipt the worker's sweep would write (it owns the proof)."""
    await _execute_sql(
        factory,
        org_id,
        """
        INSERT INTO ibex_core.erasure_store_receipts
            (org_id, memory_id, revision, store, status, verified_absent_at,
             idempotency_key)
        VALUES (:org, :memory, :revision, :store, :status,
                CASE WHEN :status = 'verified' THEN NOW() ELSE NULL END, :key)
        """,
        {
            "org": org_id,
            "memory": memory_id,
            "revision": revision,
            "store": store,
            "status": status,
            "key": f"erase:{org_id}:{memory_id}:{revision}:{store}",
        },
    )


def test_the_response_names_every_store_this_path_can_receipt() -> None:
    """The response map and the store vocabulary cannot drift apart."""
    assert set(ERASURE_STORES) == {
        "objectstore",
        "session_event",
        OBJECT_CACHE_STORE,
        HOT_CACHE_STORE,
    }


async def test_successful_eviction_records_no_failure_and_no_proof(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The request path clears the cache but does not certify that it did.

    Proof belongs to the worker (000075). What this path can honestly report is
    "no failed attempt recorded"; the store stays ``pending`` until a receipt
    exists, exactly like the object store and the session event.
    """
    org_id, agent_id, memory_id = await seed_org_agent_memory(
        session_factory, content="cache eviction success fixture"
    )
    writer = _CacheWriter()

    response = await _forget(
        session_factory,
        org_id=org_id,
        agent_id=agent_id,
        memory_id=memory_id,
        cache_writer=writer,
    )

    assert response.data.tombstoned is True
    assert writer.calls == 1, "a successful eviction is not retried"
    assert response.erasure.stores.cache == "pending"
    assert response.erasure.stores.cache_hot == "pending"
    state, error = await _attempt(session_factory, org_id=org_id, memory_id=memory_id)
    assert (state, error) == ("pending", None)
    assert await _cache_ref_count(
        session_factory, org_id=org_id, memory_id=memory_id
    ) == 2, "the forget transaction records both addresses for the worker"


async def test_exhausted_eviction_is_recorded_and_a_later_success_clears_it(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_id, agent_id, memory_id = await seed_org_agent_memory(
        session_factory, content="cache eviction failure fixture"
    )
    failing = _CacheWriter(failures=99)

    response = await _forget(
        session_factory,
        org_id=org_id,
        agent_id=agent_id,
        memory_id=memory_id,
        cache_writer=failing,
    )

    # The forget is committed, so it returns 200 with the tombstone and the
    # honest store states — not a 5xx that would invite a 409 on retry.
    assert response.data.tombstoned is True
    assert response.erasure.stores.cache == "failed"
    assert response.erasure.stores.cache_hot == "failed"
    assert response.erasure.state != "complete"
    assert failing.calls == 3, "the eviction is retried, not attempted once"

    state, error = await _attempt(session_factory, org_id=org_id, memory_id=memory_id)
    assert state == "failed"
    assert "OSError" in (error or ""), error
    assert "cache eviction failure fixture" not in (error or ""), (
        "the attempt records a reason, not memory content"
    )

    # A later successful attempt clears the failure: the ledger no longer reports
    # outstanding request-path work.
    await invalidate_forgotten_memory(
        _CacheWriter(),
        session_factory=session_factory,
        org_id=org_id,
        agent_id=agent_id,
        memory_id=memory_id,
        revision=response.data.revision,
    )
    state, error = await _attempt(session_factory, org_id=org_id, memory_id=memory_id)
    assert (state, error) == ("pending", None)
    erasure = await read_forget_erasure(
        session_factory,
        org_id=org_id,
        memory_id=memory_id,
        revision=response.data.revision,
    )
    assert erasure.stores.cache == "pending"


async def test_a_worker_receipt_wins_over_a_recorded_request_path_failure(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A receipt is proof; the attempt column is work state. Proof wins.

    The worker can settle the same revision while the request path is failing (a
    connection that failed once can fail again). Reporting ``failed`` over a
    ``verified`` receipt would tell an operator to chase work that is done.
    """
    org_id, agent_id, memory_id = await seed_org_agent_memory(
        session_factory, content="cache receipt precedence fixture"
    )
    response = await _forget(
        session_factory,
        org_id=org_id,
        agent_id=agent_id,
        memory_id=memory_id,
        cache_writer=_CacheWriter(failures=99),
    )
    revision = response.data.revision
    assert response.erasure.stores.cache == "failed"

    for store in (OBJECT_CACHE_STORE, HOT_CACHE_STORE):
        await _seed_worker_receipt(
            session_factory,
            org_id=org_id,
            memory_id=memory_id,
            revision=revision,
            store=store,
            status="verified",
        )

    erasure = await read_forget_erasure(
        session_factory, org_id=org_id, memory_id=memory_id, revision=revision
    )
    assert erasure.stores.cache == "verified"
    assert erasure.stores.cache_hot == "verified"


async def test_no_cache_configured_records_no_attempt_and_no_ref(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """No Redis cache means no copy and nothing to record."""
    org_id, agent_id, memory_id = await seed_org_agent_memory(
        session_factory, content="no cache configured fixture"
    )

    response = await _forget(
        session_factory,
        org_id=org_id,
        agent_id=agent_id,
        memory_id=memory_id,
        cache_writer=None,
    )

    assert response.erasure.stores.cache == "pending", (
        "the worker, not the tenant, answers not_applicable from the absent refs"
    )
    state, error = await _attempt(session_factory, org_id=org_id, memory_id=memory_id)
    assert (state, error) == ("pending", None)
    assert (
        await _cache_ref_count(session_factory, org_id=org_id, memory_id=memory_id) == 0
    ), "no cache means no address to record"


async def test_one_tenants_eviction_attempt_does_not_touch_another_tenant(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The attempt update is tenant-scoped, and org B's outbox row is untouched."""
    org_a, agent_a, memory_a = await seed_org_agent_memory(
        session_factory, content="cache tenancy fixture A"
    )
    org_b, agent_b, memory_b = await seed_org_agent_memory(
        session_factory, content="cache tenancy fixture B"
    )
    # Give org B its own forget so its outbox row exists to be left alone.
    await _forget(
        session_factory,
        org_id=org_b,
        agent_id=agent_b,
        memory_id=memory_b,
        cache_writer=_CacheWriter(),
    )

    await _forget(
        session_factory,
        org_id=org_a,
        agent_id=agent_a,
        memory_id=memory_a,
        cache_writer=_CacheWriter(failures=99),
    )

    assert (await _attempt(session_factory, org_id=org_b, memory_id=memory_b)) == (
        "pending",
        None,
    )
    assert (
        await _cache_ref_count(session_factory, org_id=org_b, memory_id=memory_b) == 2
    )


async def test_a_forgotten_memory_id_from_another_tenant_is_still_a_404(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Recording cache addresses must not widen the forget scope."""
    from fastapi import HTTPException

    org_a, agent_a, _memory_a = await seed_org_agent_memory(
        session_factory, content="cache scope fixture A"
    )
    _org_b, _agent_b, memory_b = await seed_org_agent_memory(
        session_factory, content="cache scope fixture B"
    )

    with pytest.raises(HTTPException) as missing:
        await _forget(
            session_factory,
            org_id=org_a,
            agent_id=agent_a,
            memory_id=memory_b,
            cache_writer=_CacheWriter(),
        )
    assert missing.value.status_code == 404


async def test_a_failure_after_delivery_is_not_recorded_as_outstanding(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Once the worker delivered the row, every store was proven.

    A request-path failure after that point is a Redis outage *after* the purge,
    not work left to do. Recording it would tell an operator to chase a store the
    worker already verified, so the attempt update is fenced on ``delivered_at``.
    """
    org_id, agent_id, memory_id = await seed_org_agent_memory(
        session_factory, content="delivered guard fixture"
    )
    response = await _forget(
        session_factory,
        org_id=org_id,
        agent_id=agent_id,
        memory_id=memory_id,
        cache_writer=_CacheWriter(),
    )
    await _execute_sql(
        session_factory,
        org_id,
        """
        UPDATE ibex_core.memory_lifecycle_outbox
           SET delivered_at = NOW(), erasure_state = 'complete'
         WHERE org_id = :org AND memory_id = :memory
        """,
        {"org": org_id, "memory": memory_id},
    )

    await invalidate_forgotten_memory(
        _CacheWriter(failures=99),
        session_factory=session_factory,
        org_id=org_id,
        agent_id=agent_id,
        memory_id=memory_id,
        revision=response.data.revision,
    )

    assert (await _attempt(session_factory, org_id=org_id, memory_id=memory_id)) == (
        "pending",
        None,
    )
