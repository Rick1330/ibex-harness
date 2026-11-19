"""A committed forget must record its cache eviction, not log it and move on.

Why this file exists: ``invalidate_forgotten_memory`` used to call the cache
writer, catch its exception and log a warning. Two failures compounded there: the
writer itself swallowed ``RedisError`` and returned, so the caller could not even
observe the failure, and nothing durable said the forgotten memory's content might
still be served from Redis for up to ``memory_cache_ttl_seconds``.

The contract asserted here, and the authority boundary behind it:

* the request path retries a transient eviction failure and, on exhaustion or a
  total budget, records an attempt as ``failed`` on the outbox row — the erasure
  ledger sees outstanding work, not a clean bill of health;
* a refusal that cannot succeed on retry (authentication, permission, wrong type)
  is recorded immediately and is not retried;
* a later success clears the attempt back to ``pending``;
* **receipts are worker-only** (000075 revoked receipt writes from the tenant), so
  this path writes no proof. A worker receipt always wins over the attempt column:
  ``verified`` is reported even if the request path recorded a failure;
* the cache addresses are recorded even when no cache writer is configured, so a
  deployment that lost its Redis configuration leaves the worker a reachable
  worklist instead of an entry nothing ever sweeps;
* a cache store with neither receipt nor failed attempt is ``pending``, never
  ``verified``.

PostgreSQL is real, so the outbox columns, refs and receipts are exercised
through RLS as the tenant. Redis is not needed here: the worker suite runs the
consumer against a real Redis and proves the keys are gone, and
``test_forget_cache_guard.py`` drives the write/forget race against real Redis.
The writer is a stub because the subject is the ledger discipline, not the wire.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cache.memory_keys import (
    HOT_CACHE_STORE,
    OBJECT_CACHE_STORE,
    memory_hot_key,
    memory_object_key,
)
from app.routers.memories import ForgetMemoryContext, forget_memory
from app.routers.memory_forget_support import (
    ERASURE_STORES,
    CacheRetryPolicy,
    ForgetAddress,
    ForgetEviction,
    invalidate_forgotten_memory,
    read_forget_erasure,
)
from app.schemas.memories import ForgetMemoryRequest
from app.write.cache import CacheInvalidationError
from tests.integration import lifecycle_erasure_support
from tests.integration.conftest import seed_org_agent_memory

pytestmark = pytest.mark.integration

_execute_sql = lifecycle_erasure_support.execute_sql
_fetch_rows = lifecycle_erasure_support.fetch_rows


@dataclass(frozen=True, slots=True)
class _Target:
    """The three identifiers one seeded memory is addressed by."""

    org_id: UUID
    agent_id: UUID
    memory_id: UUID

    @classmethod
    def from_seed(cls, seed: tuple[UUID, UUID, UUID]) -> _Target:
        return cls(org_id=seed[0], agent_id=seed[1], memory_id=seed[2])


class _CacheWriter:
    """A cache writer that fails a fixed number of times before succeeding.

    ``delay_seconds`` models a stalled ``DEL``: the socket timeout the real
    writer waits out before it raises. The request path must bound the whole
    eviction, not just the sleeps between attempts.
    """

    def __init__(
        self,
        *,
        failures: int = 0,
        delay_seconds: float = 0.0,
        error: BaseException | None = None,
    ) -> None:
        self.failures = failures
        self.delay_seconds = delay_seconds
        self.error = error
        self.calls = 0

    def object_key(self, org_id: UUID, memory_id: UUID) -> str:
        return memory_object_key(org_id, memory_id)

    def hot_key(self, org_id: UUID, agent_id: UUID) -> str:
        return memory_hot_key(org_id, agent_id)

    async def forget_memory(
        self, *, org_id: UUID, agent_id: UUID, memory_id: UUID
    ) -> None:
        del org_id, agent_id, memory_id
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error or OSError("redis is unreachable")


async def _forget(
    factory: async_sessionmaker[AsyncSession],
    target: _Target,
    cache_writer: _CacheWriter | None,
):
    ctx = ForgetMemoryContext(
        token=SimpleNamespace(org_id=target.org_id, agent_id=target.agent_id),
        session_factory=factory,
        cache_writer=cache_writer,
    )
    return await forget_memory(
        target.memory_id, ForgetMemoryRequest(expected_revision=1), ctx
    )


async def _attempt(
    factory: async_sessionmaker[AsyncSession], target: _Target
) -> tuple[str, str | None]:
    rows = await _fetch_rows(
        factory,
        target.org_id,
        """
        SELECT cache_eviction_state, cache_eviction_error
          FROM ibex_core.memory_lifecycle_outbox
         WHERE org_id = :org AND memory_id = :memory
         ORDER BY revision DESC
         LIMIT 1
        """,
        {"org": target.org_id, "memory": target.memory_id},
    )
    return str(rows[0][0]), rows[0][1]


async def _cache_refs(
    factory: async_sessionmaker[AsyncSession], target: _Target
) -> dict[str, str]:
    rows = await _fetch_rows(
        factory,
        target.org_id,
        """
        SELECT store, locator
          FROM ibex_core.memory_artifact_refs
         WHERE org_id = :org AND memory_id = :memory AND store IN ('cache','cache_hot')
         ORDER BY store
        """,
        {"org": target.org_id, "memory": target.memory_id},
    )
    return {str(store): str(locator) for store, locator in rows}


@dataclass(frozen=True, slots=True)
class _Receipt:
    """One receipt the worker's sweep would write (it owns the proof)."""

    target: _Target
    revision: int
    store: str
    status: str


async def _seed_worker_receipt(
    factory: async_sessionmaker[AsyncSession], receipt: _Receipt
) -> None:
    """Write the receipt the worker's sweep would write (it owns the proof)."""
    target = receipt.target
    await _execute_sql(
        factory,
        target.org_id,
        """
        INSERT INTO ibex_core.erasure_store_receipts
            (org_id, memory_id, revision, store, status, verified_absent_at,
             idempotency_key)
        VALUES (:org, :memory, :revision, :store, :status,
                CASE WHEN :status = 'verified' THEN NOW() ELSE NULL END, :key)
        """,
        {
            "org": target.org_id,
            "memory": target.memory_id,
            "revision": receipt.revision,
            "store": receipt.store,
            "status": receipt.status,
            "key": (
                f"erase:{target.org_id}:{target.memory_id}:{receipt.revision}:"
                f"{receipt.store}"
            ),
        },
    )


def _eviction(target: _Target, revision: int) -> ForgetEviction:
    return ForgetEviction(
        address=ForgetAddress(
            org_id=target.org_id,
            agent_id=target.agent_id,
            memory_id=target.memory_id,
        ),
        revision=revision,
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
    target = _Target.from_seed(
        await seed_org_agent_memory(
            session_factory, content="cache eviction success fixture"
        )
    )
    writer = _CacheWriter()

    response = await _forget(session_factory, target, writer)

    assert response.data.tombstoned is True
    assert writer.calls == 1, "a successful eviction is not retried"
    assert response.erasure.stores.cache == "pending"
    assert response.erasure.stores.cache_hot == "pending"
    state, error = await _attempt(session_factory, target)
    assert (state, error) == ("pending", None)
    assert await _cache_refs(session_factory, target) == {
        "cache": memory_object_key(target.org_id, target.memory_id),
        "cache_hot": memory_hot_key(target.org_id, target.agent_id),
    }, "the forget transaction records both addresses for the worker"


async def test_exhausted_eviction_is_recorded_and_a_later_success_clears_it(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    target = _Target.from_seed(
        await seed_org_agent_memory(
            session_factory, content="cache eviction failure fixture"
        )
    )
    failing = _CacheWriter(failures=99)

    response = await _forget(session_factory, target, failing)

    # The forget is committed, so it returns 200 with the tombstone and the
    # honest store states — not a 5xx that would invite a 409 on retry.
    assert response.data.tombstoned is True
    assert response.erasure.stores.cache == "failed"
    assert response.erasure.stores.cache_hot == "failed"
    assert response.erasure.state != "complete"
    assert failing.calls == 3, "a transient eviction is retried, not attempted once"

    state, error = await _attempt(session_factory, target)
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
        eviction=_eviction(target, response.data.revision),
    )
    state, error = await _attempt(session_factory, target)
    assert (state, error) == ("pending", None)
    erasure = await read_forget_erasure(
        session_factory,
        org_id=target.org_id,
        memory_id=target.memory_id,
        revision=response.data.revision,
    )
    assert erasure.stores.cache == "pending"


async def test_a_non_retryable_eviction_is_recorded_without_a_retry(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """An authentication or wrong-type failure cannot succeed on retry (A3).

    Retrying it burns the request budget and delays the honest ``failed`` state,
    so the verdict is recorded on the first refusal with its reason.
    """
    target = _Target.from_seed(
        await seed_org_agent_memory(
            session_factory, content="cache auth failure fixture"
        )
    )
    denied = _CacheWriter(
        failures=99,
        error=CacheInvalidationError(
            "memory cache eviction failed: AuthenticationError", retryable=False
        ),
    )

    await _forget(session_factory, target, denied)

    assert denied.calls == 1, "a non-retryable refusal is not retried"
    state, error = await _attempt(session_factory, target)
    assert state == "failed"
    assert "AuthenticationError" in (error or ""), error


async def test_the_request_path_eviction_has_a_total_budget(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A stalled DEL cannot hold the route open (A4).

    Three attempts at the default 0.5 s Redis socket timeout would add ~1.5 s
    before backoff even starts. The budget stops the whole eviction, records the
    outcome, and leaves the rest to the worker.
    """
    target = _Target.from_seed(
        await seed_org_agent_memory(session_factory, content="cache budget fixture")
    )
    response = await _forget(session_factory, target, _CacheWriter())
    stalled = _CacheWriter(failures=99, delay_seconds=5.0)

    started = time.perf_counter()
    await invalidate_forgotten_memory(
        stalled,
        session_factory=session_factory,
        eviction=_eviction(target, response.data.revision),
        retry=CacheRetryPolicy(total_seconds=0.1),
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 0.75, f"eviction outlived its budget: {elapsed:.3f}s"
    assert stalled.calls == 0, "the first attempt was cancelled before it completed"
    state, error = await _attempt(session_factory, target)
    assert state == "failed"
    assert "budget" in (error or ""), error


async def test_the_default_budget_bounds_a_stalled_eviction(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Measure the real worst case with the default policy in force.

    The writer sleeps longer than the budget on every attempt, which is what a
    ``DEL`` stalled to the socket timeout looks like to the route. The response
    must return within the budget plus a small margin, and the attempt must say
    the budget was the reason.
    """
    target = _Target.from_seed(
        await seed_org_agent_memory(session_factory, content="cache stalled fixture")
    )
    response = await _forget(session_factory, target, _CacheWriter())
    stalled = _CacheWriter(failures=99, delay_seconds=0.5)

    started = time.perf_counter()
    await invalidate_forgotten_memory(
        stalled,
        session_factory=session_factory,
        eviction=_eviction(target, response.data.revision),
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 1.5, (
        f"default eviction budget did not bound the request: {elapsed:.3f}s"
    )
    state, error = await _attempt(session_factory, target)
    assert state == "failed"
    assert "budget" in (error or ""), error


async def test_a_worker_receipt_wins_over_a_recorded_request_path_failure(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A receipt is proof; the attempt column is work state. Proof wins.

    The worker can settle the same revision while the request path is failing (a
    connection that failed once can fail again). Reporting ``failed`` over a
    ``verified`` receipt would tell an operator to chase work that is done.
    """
    target = _Target.from_seed(
        await seed_org_agent_memory(
            session_factory, content="cache receipt precedence fixture"
        )
    )
    response = await _forget(
        session_factory, target, _CacheWriter(failures=99)
    )
    revision = response.data.revision
    assert response.erasure.stores.cache == "failed"

    for store in (OBJECT_CACHE_STORE, HOT_CACHE_STORE):
        await _seed_worker_receipt(
            session_factory, _Receipt(target, revision, store, "verified")
        )

    erasure = await read_forget_erasure(
        session_factory,
        org_id=target.org_id,
        memory_id=target.memory_id,
        revision=revision,
    )
    assert erasure.stores.cache == "verified"
    assert erasure.stores.cache_hot == "verified"


async def test_no_cache_writer_still_records_the_derived_addresses(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A deployment without a cache writer still records where the copies live.

    An absent ref means "not recorded", never "proved absent" (A5). The worker
    reaches these addresses and reports ``failed`` if Redis is unconfigured,
    which is honest about what it cannot prove.
    """
    target = _Target.from_seed(
        await seed_org_agent_memory(
            session_factory, content="no cache writer configured fixture"
        )
    )

    response = await _forget(session_factory, target, None)

    assert response.erasure.stores.cache == "pending", (
        "the worker, not the tenant, answers for the cache stores"
    )
    state, error = await _attempt(session_factory, target)
    assert (state, error) == ("pending", None)
    assert await _cache_refs(session_factory, target) == {
        "cache": memory_object_key(target.org_id, target.memory_id),
        "cache_hot": memory_hot_key(target.org_id, target.agent_id),
    }, "the addresses are derivable, so they are recorded regardless of the writer"


async def test_one_tenants_eviction_attempt_does_not_touch_another_tenant(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The attempt update is tenant-scoped, and org B's outbox row is untouched."""
    target_a = _Target.from_seed(
        await seed_org_agent_memory(session_factory, content="cache tenancy fixture A")
    )
    target_b = _Target.from_seed(
        await seed_org_agent_memory(session_factory, content="cache tenancy fixture B")
    )
    # Give org B its own forget so its outbox row exists to be left alone.
    await _forget(session_factory, target_b, _CacheWriter())

    await _forget(session_factory, target_a, _CacheWriter(failures=99))

    assert (await _attempt(session_factory, target_b)) == ("pending", None)
    assert len(await _cache_refs(session_factory, target_b)) == 2


async def test_a_forgotten_memory_id_from_another_tenant_is_still_a_404(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Recording cache addresses must not widen the forget scope."""
    from fastapi import HTTPException

    target_a = _Target.from_seed(
        await seed_org_agent_memory(session_factory, content="cache scope fixture A")
    )
    other = _Target.from_seed(
        await seed_org_agent_memory(session_factory, content="cache scope fixture B")
    )

    with pytest.raises(HTTPException) as missing:
        await _forget(
            session_factory,
            _Target(
                org_id=target_a.org_id,
                agent_id=target_a.agent_id,
                memory_id=other.memory_id,
            ),
            _CacheWriter(),
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
    target = _Target.from_seed(
        await seed_org_agent_memory(session_factory, content="delivered guard fixture")
    )
    response = await _forget(session_factory, target, _CacheWriter())
    await _execute_sql(
        session_factory,
        target.org_id,
        """
        UPDATE ibex_core.memory_lifecycle_outbox
           SET delivered_at = NOW(), erasure_state = 'complete'
         WHERE org_id = :org AND memory_id = :memory
        """,
        {"org": target.org_id, "memory": target.memory_id},
    )

    await invalidate_forgotten_memory(
        _CacheWriter(failures=99),
        session_factory=session_factory,
        eviction=_eviction(target, response.data.revision),
    )

    assert (await _attempt(session_factory, target)) == ("pending", None)
