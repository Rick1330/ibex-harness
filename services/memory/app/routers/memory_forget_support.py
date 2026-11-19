"""Forget (tombstone) orchestration for the memory write routes.

Forget is a destructive lifecycle operation: it tombstones the row inside its
own transaction, records the addresses of every external copy, and then evicts
the caches derived from it. Database and lifecycle failures are mapped to stable
HTTP envelopes here so the route only sequences the calls.

Cache eviction is not best-effort. A cached memory object carries the memory's
``content`` for up to ``memory_cache_ttl_seconds``, so an eviction that fails and
is only logged leaves a forgotten memory readable — a disclosure the request has
already reported as done. The eviction is retried with bounded backoff, and when
the retries are exhausted the outcome is written to the outbox row the worker
already reads, so the erasure ledger answers "is anything still cached for this
memory?" from the database and the worker's sweep retries the eviction from the
artifact refs the forget transaction recorded. The request never waits on an
unbounded retry: the tombstone is committed, so the response must return promptly
and truthfully rather than hang behind a cache outage.

Who may write what is deliberate. 000075 revoked receipt writes from the tenant
identity: a request path that can write a receipt can forge ``verified`` for a
store it never cleared. This module therefore writes only the *attempt* columns
on the outbox row (``pending``/``failed``, a vocabulary with no ``verified``
value). The proof stays with ``ibex.worker.lifecycle.erase_memory``. The response
shows a store as ``failed`` from the attempt column only while no receipt exists;
a receipt always wins.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.cache.memory_keys import HOT_CACHE_STORE, OBJECT_CACHE_STORE
from app.db import session_with_org
from app.exceptions import ConflictError, MemoryNotFoundError
from app.lifecycle import ForgetCacheScope, ForgetMemory, forget_memory_session
from app.schemas.memories import ErasureStatus, ErasureStores

logger = logging.getLogger(__name__)

#: The stores whose proof ``ibex.worker.lifecycle.erase_memory`` can produce. One
#: receipt per store is written by that consumer; a store with no receipt yet is
#: reported as ``pending`` rather than assumed clean, unless the request path
#: recorded a failed attempt for the cache stores.
#:
#: ClickHouse is not here: no producer records a per-memory ClickHouse locator, so
#: the consumer cannot prove that store, and a receipt for it would be a claim
#: nobody made. It is erased by the org-deletion saga instead, which proves
#: absence org-wide. Reporting it as ``not_applicable`` would certify an erasure
#: that never ran.
#:
#: The two cache stores are separate because the purge verbs differ: the object
#: entry is a string removed with DEL, the hot sorted set is a key whose single
#: member is removed with ZREM. A DEL of the hot key would evict every other
#: memory's hot score for that agent.
_CACHE_STORES: tuple[str, ...] = (OBJECT_CACHE_STORE, HOT_CACHE_STORE)

ERASURE_STORES: tuple[str, ...] = (
    "objectstore",
    "session_event",
    *_CACHE_STORES,
)

#: Cache eviction retry policy. Three attempts with a 50 ms base stay under
#: ~0.4 s of added request latency on the worst path, which is the whole point:
#: a committed forget must not hang behind Redis. Exhaustion is not silent — the
#: outbox attempt column records it and the worker retries from the refs.
_CACHE_RETRY_ATTEMPTS = 3
_CACHE_RETRY_BASE_SECONDS = 0.05
_CACHE_RETRY_CAP_SECONDS = 0.4
_CACHE_RETRY_JITTER_FRACTION = 0.25
_ERROR_MAX_CHARS = 200

#: The outbox row's job state and the request path's cache attempt, in one read.
#: The attempt column is tenant-writable work state, not proof: its domain is
#: ``pending``/``failed`` (000078), so it can never be read as "cache is gone".
_OUTBOX_STATE_SQL = """
SELECT erasure_state, cache_eviction_state
  FROM ibex_core.memory_lifecycle_outbox
 WHERE org_id = :org_id
   AND memory_id = :memory_id
   AND revision = :revision
 ORDER BY occurred_at DESC, id
 LIMIT 1
"""

_RECEIPT_STATUSES_SQL = """
SELECT store, status
  FROM ibex_core.erasure_store_receipts
 WHERE org_id = :org_id
   AND memory_id = :memory_id
   AND revision = :revision
"""

#: Column-scoped UPDATE the tenant may perform (000078): the two attempt columns
#: and nothing else. The settle columns belong to ``ibex_erasure`` (000075), so
#: this statement cannot deliver the row or claim its work complete. It is also
#: fenced on ``delivered_at IS NULL``: once the worker has delivered the row, every
#: store was proven and a later request-path failure is a Redis outage after the
#: purge, not outstanding work — recording it would contradict a receipt that
#: already says ``verified``.
_RECORD_CACHE_EVICTION_SQL = """
UPDATE ibex_core.memory_lifecycle_outbox
   SET cache_eviction_state = :state,
       cache_eviction_error = :error
 WHERE org_id = :org_id
   AND memory_id = :memory_id
   AND revision = :revision
   AND delivered_at IS NULL
"""


def forget_cache_scope(
    cache_writer: Any, *, org_id: UUID, agent_id: UUID, memory_id: UUID
) -> ForgetCacheScope:
    """The cache addresses the forget transaction must record.

    ``None`` means no Redis cache is configured for this deployment
    (``_configure_redis`` returns no writer when ``redis_url`` is unset), so the
    scope is empty, no ref is recorded, and the worker reports ``not_applicable``
    for the cache stores instead of a purge of an address that never existed.
    """
    if cache_writer is None:
        return ForgetCacheScope()
    return ForgetCacheScope(
        object_keys=(cache_writer.object_key(org_id, memory_id),),
        hot_keys=(cache_writer.hot_key(org_id, agent_id),),
    )


async def forget_memory_with_error_mapping(
    *,
    session_factory: Any,
    command: ForgetMemory,
    cache_scope: ForgetCacheScope | None = None,
) -> int:
    """Tombstone a memory, mapping lifecycle and database failures to HTTP."""
    try:
        async with session_factory() as session, session.begin():
            return await forget_memory_session(
                session, command, cache_scope=cache_scope or ForgetCacheScope()
            )
    except MemoryNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Memory not found"},
        ) from exc
    except ConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database unavailable"},
        ) from exc


async def invalidate_forgotten_memory(
    cache_writer: Any,
    *,
    session_factory: Any,
    org_id: UUID,
    agent_id: UUID,
    memory_id: UUID,
    revision: int,
    rng: Any = random.random,
    sleep: Any = asyncio.sleep,
) -> None:
    """Evict both cached copies and record the outcome where the ledger reads.

    Runs after the forget transaction commits. Never raises: the tombstone is
    already durable, and a 5xx here would invite a retry that the lifecycle fence
    answers with 409 for a memory that is in fact forgotten. A failure is
    recorded as an outbox attempt, not logged and dropped, and the worker's
    receipt later supersedes it.
    """
    state, error = await _purge_cache(
        cache_writer,
        org_id=org_id,
        agent_id=agent_id,
        memory_id=memory_id,
        rng=rng,
        sleep=sleep,
    )
    if cache_writer is None:
        # No cache in this deployment: nothing was attempted and nothing is
        # outstanding. The worker records `not_applicable` from the absent refs.
        return
    await _record_cache_eviction(
        session_factory,
        org_id=org_id,
        memory_id=memory_id,
        revision=revision,
        state=state,
        error=error,
    )


async def _purge_cache(
    cache_writer: Any,
    *,
    org_id: UUID,
    agent_id: UUID,
    memory_id: UUID,
    rng: Any,
    sleep: Any,
) -> tuple[str, str | None]:
    """Delete both cached copies with bounded retry; return the attempt state."""
    if cache_writer is None:
        return "pending", None
    last: BaseException | None = None
    for attempt in range(1, _CACHE_RETRY_ATTEMPTS + 1):
        try:
            await cache_writer.forget_memory(
                org_id=org_id, agent_id=agent_id, memory_id=memory_id
            )
            return "pending", None
        except Exception as exc:  # noqa: BLE001 — any eviction failure is recorded
            last = exc
            if attempt < _CACHE_RETRY_ATTEMPTS:
                await sleep(_cache_backoff_seconds(attempt, rng))
    logger.warning(  # NOSONAR pythonsecurity:S5145 - UUID hex is hex-only, not free text
        "memory cache eviction exhausted its retries; recorded for the erasure sweep "
        "org_id=%s memory_id=%s error_type=%s",
        org_id.hex,
        memory_id.hex,
        type(last).__name__,
    )
    return "failed", _error_reason(last)


def _cache_backoff_seconds(attempt: int, rng: Any) -> float:
    """Capped exponential delay with bounded jitter for attempt ``attempt`` (1-based)."""
    base = min(_CACHE_RETRY_BASE_SECONDS * (2 ** (attempt - 1)), _CACHE_RETRY_CAP_SECONDS)
    jitter = _CACHE_RETRY_JITTER_FRACTION * (2.0 * rng() - 1.0)
    return max(0.0, min(_CACHE_RETRY_CAP_SECONDS, base * (1.0 + jitter)))


def _error_reason(exc: BaseException | None) -> str | None:
    """Content-free reason: an exception type and text, never memory content.

    The text is truncated and the writer's message is fixed, but the truncation
    is the guard: this value is stored in the outbox and read by operators, and
    no exception message may become an unbounded field.
    """
    if exc is None:
        return None
    return f"{type(exc).__name__}: {exc}"[:_ERROR_MAX_CHARS]


async def _record_cache_eviction(
    session_factory: Any,
    *,
    org_id: UUID,
    memory_id: UUID,
    revision: int,
    state: str,
    error: str | None,
) -> None:
    """Write the request path's cache attempt, or record that it is unreadable.

    A failure here is logged and swallowed for the same reason the read path
    degrades to ``pending``: the forget is committed, so the response must not
    become a 503. The outstanding work is still reachable — the forget
    transaction recorded the cache refs, so the worker evicts them regardless.
    """
    params = {
        "org_id": str(org_id),
        "memory_id": str(memory_id),
        "revision": revision,
        "state": state,
        "error": error,
    }
    try:
        async with session_with_org(session_factory, str(org_id)) as session:
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    _RECORD_CACHE_EVICTION_SQL
                ),
                params,
            )
    except Exception:  # a committed forget must still return
        logger.warning(  # NOSONAR pythonsecurity:S5145 - UUID hex is hex-only, not free text
            "memory cache attempt could not be recorded org_id=%s memory_id=%s revision=%s",
            org_id.hex,
            memory_id.hex,
            revision,
            exc_info=True,
        )


async def read_forget_erasure(
    session_factory: Any,
    *,
    org_id: UUID,
    memory_id: UUID,
    revision: int,
) -> ErasureStatus:
    """Report the erasure proof this forget produced, without inventing one.

    The job state comes from the outbox row the forget wrote and the per-store
    detail from the receipts the consumer wrote; the consumer derives the former
    from the latter, so the two cannot disagree. A cache store with no receipt
    but a recorded failed attempt is reported ``failed`` — work the sweep will
    retry, not a clean result. Reading them is deliberately separate from the
    forget transaction: erasure happens after it commits, and this route must not
    report ``complete`` for work that has not run.

    A read failure degrades to ``pending`` rather than failing the request. The
    tombstone is already committed, so a 503 here would invite a retry that the
    lifecycle fence answers with 409 for a memory that is in fact forgotten;
    "no proof recorded yet" is both true and actionable.
    """
    params = {"org_id": org_id, "memory_id": memory_id, "revision": revision}
    try:
        async with session_with_org(session_factory, str(org_id)) as session:
            row = (
                await session.execute(text(_OUTBOX_STATE_SQL), params)
            ).first()
            rows = (await session.execute(text(_RECEIPT_STATUSES_SQL), params)).all()
    except Exception:
        logger.warning(  # NOSONAR pythonsecurity:S5145 - UUID hex is hex-only, not free text
            "forget erasure state unreadable org_id=%s memory_id=%s revision=%s",
            org_id.hex,
            memory_id.hex,
            revision,
            exc_info=True,
        )
        return ErasureStatus()
    job_state = row[0] if row is not None else None
    cache_failed = row is not None and row[1] == "failed"
    return _erasure_status(job_state, rows, cache_failed)


#: Values the response contract accepts. A row can only hold these (CHECK
#: constraints in 000074/000073/000078), but a mapping step that raised on an
#: unexpected value would turn a committed forget into a 500, so anything else
#: degrades to "no proof yet" instead.
_JOB_STATES = frozenset({"pending", "partial", "complete", "failed"})
_STORE_STATES = frozenset({"pending", "verified", "failed", "not_applicable"})


def _erasure_status(
    job_state: str | None, rows: Any, cache_failed: bool = False
) -> ErasureStatus:
    """Map the outbox state, the attempts, and the receipts onto the contract.

    Precedence: a receipt is proof and always wins. A cache store with no receipt
    but a failed request-path attempt is ``failed``. Everything else with no
    receipt is ``pending``. The attempt flag is consulted only for the two cache
    stores, because only those have a tenant-writable attempt column.
    """
    statuses = {str(store): str(status) for store, status in rows}
    stores = ErasureStores(
        **{
            store: _store_state(
                statuses.get(store), store=store, cache_failed=cache_failed
            )
            for store in ERASURE_STORES
        }
    )
    state = job_state if job_state in _JOB_STATES else "pending"
    return ErasureStatus(state=state, stores=stores)


def _store_state(status: str | None, *, store: str, cache_failed: bool) -> str:
    """One store's state: receipt first, then the cache attempt, then pending."""
    if status in _STORE_STATES:
        return status
    if cache_failed and store in _CACHE_STORES:
        return "failed"
    return "pending"
