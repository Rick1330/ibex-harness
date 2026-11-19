"""Memory-lifecycle erasure consumer: prove a forgotten memory is gone everywhere.

The forget path (``services/memory/app/lifecycle.py``) tombstones the memory row
and writes one ``memory_lifecycle_outbox`` row in the same transaction. Nothing
consumed those rows, so a forget could report success while the memory's
object-store capture, its ClickHouse evidence and the ``session_events`` row that
carried it still existed. This module is that consumer.

Contract, in the order the details are easy to get wrong:

* Only erasure events are consumed: ``forgotten``, ``purged``, ``expired``. A
  ``created`` / ``content_updated`` / ``superseded`` row describes a memory that
  still exists, and erasing its refs would delete live data. The claim function
  in migration 000074 enforces the same set in SQL.
* One receipt per ``(memory, revision, store)``, written with ``ON CONFLICT DO
  UPDATE`` on the 000073 unique key, so a redelivered task writes no second row
  and a retry resumes instead of duplicating.
* ``verified`` requires the store to have confirmed absence. An unreachable store
  is ``failed`` — never ``verified``, and never ``not_applicable`` (which means
  "this memory has no copy in that store" and nothing else). ``org_deletion.py``
  keeps the same distinction at org scope; see ``_all_receipts_satisfied``.
* A store already proven for this revision is not re-staged: the first proof
  stands and its ``verified_absent_at`` is not overwritten by a retry.
* A row whose ``revision`` is lower than one already delivered for the same
  memory is retired, not erased: the newer revision describes the same memory's
  end state, so this row has nothing left to prove and copies the newer row's
  state rather than inventing one. Retiring (rather than never claiming) is what
  keeps the pending set finite.
* ``erasure_state`` becomes ``complete`` only when every receipt is ``verified``
  or ``not_applicable``; otherwise ``partial`` with exponential backoff, until
  ``erasure_deadline`` passes and the row is terminally ``failed`` so a
  permanently unreachable store cannot retry forever.
* Artifact refs are kept after a verified erasure. The receipt is the proof and
  the ref is the address the proof refers to; deleting the ref would make the
  address unrecoverable, which is exactly the gap 000072 exists to close.
* ``RECEIPT_STORES`` is the set of stores whose absence this consumer can *prove*,
  because a producer records a ref for every copy. ClickHouse is deliberately not
  in it: no producer writes a per-memory ClickHouse locator (the evidence relay
  projects session resources only), so an absent ClickHouse ref cannot be read as
  "this memory has no ClickHouse copy". A ref that does name ClickHouse is still
  erased and receipted; a memory with no such ref simply makes no ClickHouse
  claim, instead of the false ``not_applicable`` a missing ref used to produce.
* The two cache stores are the disclosure fix. ``cache`` is the object entry that
  carries the memory's ``content``; ``cache_hot`` is the per-agent hot sorted set,
  whose member is removed with ZREM rather than the key with DEL — the key holds
  every other memory's score for that agent. A cache locator is caller-written
  text, so each stage refuses a key outside its own ``<org>:{namespace}:`` before
  deleting anything, and an unreachable or unconfigured Redis is ``failed``, never
  ``verified``.

Tenant boundary: discovery runs through the ``SECURITY DEFINER`` claim function
(the outbox is RLS-scoped, so a sweep with no tenant selected would see nothing)
and returns identifiers only. Every statement after the claim runs through
``session_as_app_org`` — ``ibex_app`` plus ``app.current_org_id`` — so RLS fences
the row's own org and the consumer cannot reach another tenant's refs or receipts.
The one exception is the ``session_events`` DELETE: that table is an append-only
audit trail, and ``ibex_app`` deliberately holds no DELETE on it, so that single
statement runs through ``session_as_purge_org`` — ``ibex_purge`` plus the same
org GUC — which is the only identity 000064 grants the verb to. The ClickHouse
mutation carries the org predicate explicitly because ClickHouse has no RLS.

Deadlines: ``lifecycle_erasure_store_timeout_seconds`` (120 s) per store and
``lifecycle_erasure_job_timeout_seconds`` (900 s) for the whole row. Both are
hard stops that become a ``failed`` receipt rather than a longer wait. The Celery
task limits are derived from the job budget plus settlement headroom, so a legal
longer budget is not killed by a fixed task limit before its own deadline.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from prometheus_client import Counter
from sqlalchemy import text

from app.celery_app import celery_app
from app.config import get_settings
from app.db import (
    create_engine,
    create_session_factory,
    session_as_app_org,
    session_as_erasure_org,
    session_as_purge_org,
    session_unpinned,
)
from app.objectstore_client import delete_uri, object_exists
from app.task_names import TASK_LIFECYCLE_ERASE_MEMORY
from app.tasks import org_deletion_stores as _stores
from app.tasks.base import IbexTask

logger = logging.getLogger(__name__)

#: Outbox event types that end a memory. The claim function repeats this set in
#: SQL; ``test_lifecycle_erasure_contract`` fails if the two ever disagree.
ERASURE_EVENT_TYPES: tuple[str, ...] = ("forgotten", "purged", "expired")

#: Stores whose erasure this consumer can prove: a producer records a ref for
#: every copy it writes (``capture_redaction`` for object store and session event,
#: the forget transaction for the two cache structures). ClickHouse is absent on
#: purpose — nothing writes a per-memory ClickHouse ref, so "no ref" would mean
#: "not checked", not "no copy", and a receipt saying ``not_applicable`` there
#: would certify an erasure nobody performed. A ref that names a store outside
#: this set is still staged (see ``_stores_to_stage``).
#:
#: ``cache`` is the object cache entry that carries the memory's content; the
#: DEL of that key is the disclosure fix. ``cache_hot`` is the per-agent hot
#: sorted set, whose single member is removed rather than the key itself: a DEL
#: there would evict every other memory's hot score for that agent.
RECEIPT_STORES: tuple[str, ...] = ("objectstore", "session_event", "cache", "cache_hot")

#: Receipt statuses that prove a store without further work.
SATISFIED_RECEIPT_STATUSES = frozenset({"verified", "not_applicable"})

#: Rows claimed per sweep run. One at a time keeps the lease and the per-row
#: deadline accounting honest; the beat supplies the throughput.
_CLAIM_BATCH = 1

_RETRY_BASE_SECONDS = 30
_RETRY_CAP_SECONDS = 3600
#: Fraction of the capped delay that is randomized either way. Bounded so a
#: retry stays inside ``_RETRY_CAP_SECONDS`` while two erasures hitting the same
#: outage do not wake at the same instant.
_RETRY_JITTER_FRACTION = 0.25
_ERROR_MAX_CHARS = 300

#: Headroom over the configured job budget for writing receipts and settling
#: the outbox row after the last store stage, plus a further grace before the
#: process is killed. The Celery soft limit must be strictly larger than the
#: budget the sweep enforces, or a legal configuration is killed mid-settle.
_ERASURE_SETTLEMENT_HEADROOM_SECONDS = 60.0
_ERASURE_KILL_GRACE_SECONDS = 60.0


class PermanentErasureFailure(RuntimeError):
    """A locator that cannot succeed on retry.

    An unsupported scheme, a malformed locator, or a key outside the tenant
    prefix is a property of the stored address, not a transient outage. Retrying
    it until ``erasure_deadline`` only delays the honest ``failed`` state, so the
    consumer records the failure and stops scheduling attempts.
    """


ERASURE_OUTCOME = Counter(
    "ibex_worker_memory_erasure_total",
    "Memory erasure outbox rows settled, by resulting state",
    ["state"],
)
ERASURE_STORE = Counter(
    "ibex_worker_memory_erasure_store_total",
    "Per-store outcome of a memory erasure",
    ["store", "status"],
)

# SECURITY DEFINER claim: the outbox is RLS-scoped to app.current_org_id, and a
# scheduled consumer has no tenant to select, so discovery cannot run as a
# tenant. The function returns identifiers only; everything after it is
# tenant-scoped.
_CLAIM_SQL = """
SELECT id::text AS id, org_id::text AS org_id, memory_id::text AS memory_id,
       revision, attempts, event_type, erasure_deadline
  FROM ibex_core.memory_lifecycle_claim_erasure(
           CAST(:claim_limit AS integer),
           CAST(:lease_seconds AS double precision),
           CAST(:deadline_seconds AS double precision)
       )
"""

_REFS_SQL = """
SELECT store, locator
  FROM ibex_core.memory_artifact_refs
 WHERE org_id = CAST(:org_id AS uuid)
   AND memory_id = CAST(:memory_id AS uuid)
 ORDER BY store, locator
"""

_RECEIPTS_SQL = """
SELECT store, status
  FROM ibex_core.erasure_store_receipts
 WHERE org_id = CAST(:org_id AS uuid)
   AND memory_id = CAST(:memory_id AS uuid)
   AND revision = :revision
"""

# The unique key from 000073 is the idempotency mechanism: a redelivery of the
# same (org, memory, revision, store) updates the one row instead of adding one.
# The conflict guard is monotonic: a receipt that already says ``verified`` is
# never replaced by a weaker status. The request path can write a ``failed``
# cache receipt while this sweep is settling the same revision, and a late
# failure must not overwrite the proof this run earned.
_UPSERT_RECEIPT_SQL = """
INSERT INTO ibex_core.erasure_store_receipts (
    org_id, memory_id, revision, store, status, verified_absent_at,
    idempotency_key, error
) VALUES (
    CAST(:org_id AS uuid), CAST(:memory_id AS uuid), :revision, :store, :status,
    CASE WHEN :status = 'verified' THEN NOW() ELSE NULL END,
    :idempotency_key, :error
)
ON CONFLICT (org_id, memory_id, revision, store) DO UPDATE
   SET status = EXCLUDED.status,
       verified_absent_at = EXCLUDED.verified_absent_at,
       error = EXCLUDED.error,
       idempotency_key = EXCLUDED.idempotency_key
 WHERE ibex_core.erasure_store_receipts.status <> 'verified'
    OR EXCLUDED.status = 'verified'
"""

#: Every settle statement names the org as well as the row. RLS already fences
#: the row, but AGENTS.md §4.1 requires the explicit predicate in the query too:
#: one defence that is switched off by a role attribute or a policy edit must not
#: be the only thing standing between one tenant's settle and another's row.
_COMPLETE_SQL = """
UPDATE ibex_core.memory_lifecycle_outbox
   SET erasure_state = 'complete',
       delivered_at = NOW(),
       locked_until = NULL
 WHERE id = CAST(:id AS uuid)
   AND org_id = CAST(:org_id AS uuid)
   AND delivered_at IS NULL
   AND attempts = CAST(:attempts AS integer)
"""

_RETRY_SQL = """
UPDATE ibex_core.memory_lifecycle_outbox
   SET erasure_state = 'partial',
       available_at = NOW() + make_interval(secs => :delay_seconds),
       locked_until = NULL
 WHERE id = CAST(:id AS uuid)
   AND org_id = CAST(:org_id AS uuid)
   AND delivered_at IS NULL
   AND attempts = CAST(:attempts AS integer)
"""

_FAIL_SQL = """
UPDATE ibex_core.memory_lifecycle_outbox
   SET erasure_state = 'failed',
       locked_until = NULL
 WHERE id = CAST(:id AS uuid)
   AND org_id = CAST(:org_id AS uuid)
   AND delivered_at IS NULL
   AND attempts = CAST(:attempts AS integer)
"""

#: Settlement fence. The row is locked and the attempt this run claimed is
#: checked before any receipt is written, so a worker whose lease expired cannot
#: overwrite a newer worker's proof with its own outcome.
_CLAIM_STILL_HELD_SQL = """
SELECT id
  FROM ibex_core.memory_lifecycle_outbox
 WHERE id = CAST(:id AS uuid)
   AND org_id = CAST(:org_id AS uuid)
   AND delivered_at IS NULL
   AND attempts = CAST(:attempts AS integer)
 FOR UPDATE
"""

# A row superseded by a newer delivered revision is retired with the newer row's
# state: the erasure for this memory is whatever the newest revision proved.
_RETIRE_STALE_SQL = """
UPDATE ibex_core.memory_lifecycle_outbox AS stale
   SET delivered_at = NOW(),
       locked_until = NULL,
       erasure_state = newer.erasure_state
  FROM (
        SELECT erasure_state
          FROM ibex_core.memory_lifecycle_outbox
         WHERE org_id = CAST(:org_id AS uuid)
           AND memory_id = CAST(:memory_id AS uuid)
           AND delivered_at IS NOT NULL
           AND revision > :revision
         ORDER BY revision DESC
         LIMIT 1
       ) AS newer
 WHERE stale.id = CAST(:id AS uuid)
   AND stale.org_id = CAST(:org_id AS uuid)
   AND stale.delivered_at IS NULL
   AND stale.attempts = CAST(:attempts AS integer)
"""

_DELETE_SESSION_EVENT_SQL = """
DELETE FROM ibex_core.session_events
 WHERE org_id = CAST(:org_id AS uuid)
   AND id = CAST(:event_id AS bigint)
"""

_COUNT_SESSION_EVENT_SQL = """
SELECT count(*)
  FROM ibex_core.session_events
 WHERE org_id = CAST(:org_id AS uuid)
   AND id = CAST(:event_id AS bigint)
"""


@dataclass(frozen=True, slots=True)
class _ClaimedRow:
    """One leased outbox row, as the claim function returned it."""

    row_id: str
    org_id: str
    memory_id: str
    revision: int
    attempts: int
    event_type: str
    deadline: datetime | None


@dataclass(frozen=True, slots=True)
class _Erasure:
    """A claimed row plus the dependencies its store stages need."""

    row: _ClaimedRow
    settings: Any
    factory: Any


@dataclass(frozen=True, slots=True)
class _StoreTarget:
    """One store and the locators the artifact refs recorded for it."""

    store: str
    locators: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _StoreOutcome:
    """What one store proved, and whether this run is what proved it."""

    store: str
    status: str
    error: str | None = None
    fresh: bool = True
    permanent: bool = False


def _task_limits(job_timeout_seconds: float) -> tuple[int, int]:
    """Celery (soft, hard) limits for one erasure job budget.

    Derived rather than fixed: ``lifecycle_erasure_job_timeout_seconds`` is
    configurable up to 3600 s, so a fixed 900 s soft limit killed a legal 1800 s
    job before its own deadline. Settlement (receipts and the outbox update)
    runs after the last store stage, so the soft limit carries headroom for it
    and the hard limit adds a further grace before the process is killed.
    """
    soft = int(job_timeout_seconds + _ERASURE_SETTLEMENT_HEADROOM_SECONDS)
    return soft, soft + int(_ERASURE_KILL_GRACE_SECONDS)


_ERASURE_SOFT_LIMIT, _ERASURE_TIME_LIMIT = _task_limits(
    get_settings().lifecycle_erasure_job_timeout_seconds
)


@celery_app.task(
    bind=True,
    base=IbexTask,
    name=TASK_LIFECYCLE_ERASE_MEMORY,
    queue="maintenance",
    # Derived from the configured job budget plus settlement headroom; a fixed
    # limit here would kill a legal longer budget before the sweep's own
    # deadline. ``configure_erasure_task_limits`` re-applies the derivation from
    # the worker's loaded settings and is the seam the tests drive.
    soft_time_limit=_ERASURE_SOFT_LIMIT,
    time_limit=_ERASURE_TIME_LIMIT,
)
def erase_memory(self: IbexTask, **kwargs: Any) -> dict[str, Any]:
    """Sweep undelivered memory erasure rows and settle each one."""
    del self, kwargs
    return asyncio.run(_run_sweep())


def configure_erasure_task_limits(job_timeout_seconds: float) -> None:
    """Apply the derived Celery limits to the registered task.

    Called at import with the loaded settings; exposed so a test can prove a
    non-default job budget is reflected in the registered task's limits.
    """
    erase_memory.soft_time_limit, erase_memory.time_limit = _task_limits(
        job_timeout_seconds
    )


async def _run_sweep(
    *, settings: Any | None = None, claim_batch: int = _CLAIM_BATCH
) -> dict[str, Any]:
    """Claim and settle erasure rows until the batch or the job deadline runs out."""
    cfg = settings or get_settings()
    if not cfg.database_url:
        logger.info("memory erasure skipped: missing database url")
        return {"status": "skipped", "reason": "missing_dsn"}
    engine = create_engine(cfg)
    factory = create_session_factory(engine)
    job_deadline = time.monotonic() + cfg.lifecycle_erasure_job_timeout_seconds
    tally = {"claimed": 0, "complete": 0, "partial": 0, "failed": 0, "retired": 0}
    try:
        for _ in range(claim_batch):
            if time.monotonic() >= job_deadline:
                break
            row = await _claim_one(factory, cfg)
            if row is None:
                break
            tally["claimed"] += 1
            tally[await _erase_row(factory, cfg, row, job_deadline)] += 1
        return {"status": "ok", **tally}
    finally:
        await engine.dispose()


async def _claim_one(factory: Any, settings: Any) -> _ClaimedRow | None:
    """Lease the next erasure row, or None when nothing is claimable."""
    params = {
        "claim_limit": _CLAIM_BATCH,
        "lease_seconds": float(settings.lifecycle_erasure_job_timeout_seconds),
        "deadline_seconds": float(settings.lifecycle_erasure_job_timeout_seconds),
    }
    async with session_unpinned(factory) as session:
        row = (await session.execute(text(_CLAIM_SQL), params)).mappings().first()
    if row is None:
        return None
    return _ClaimedRow(
        row_id=str(row["id"]),
        org_id=str(row["org_id"]),
        memory_id=str(row["memory_id"]),
        revision=int(row["revision"]),
        attempts=int(row["attempts"]),
        event_type=str(row["event_type"]),
        deadline=row["erasure_deadline"],
    )


async def _erase_row(
    factory: Any, settings: Any, row: _ClaimedRow, job_deadline: float
) -> str:
    """Erase one memory's external copies and settle its outbox row."""
    if await _retire_if_stale(factory, row):
        logger.info(
            "memory erasure retired as superseded row_id=%s org_id=%s memory_id=%s revision=%s",
            row.row_id,
            row.org_id,
            row.memory_id,
            row.revision,
        )
        return "retired"
    refs, existing = await _read_erasure_state(factory, row)
    erasure = _Erasure(row=row, settings=settings, factory=factory)
    outcomes = [
        await _erase_store(
            erasure, _StoreTarget(store, refs.get(store, ())), existing, job_deadline
        )
        for store in _stores_to_stage(refs)
    ]
    return await _settle(erasure, outcomes, refs)


def _stores_to_stage(refs: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    """Stores this run settles: the provable set, plus any store a ref names.

    A store outside ``RECEIPT_STORES`` has no producer recording its refs, so an
    absent ref says nothing about whether a copy exists and must not become a
    ``not_applicable`` receipt. A ref that *does* name it is a different fact: the
    copy is known to exist, so it is staged and receipted like any other store,
    and a failure there blocks ``complete``.
    """
    return tuple(dict.fromkeys((*RECEIPT_STORES, *sorted(refs))))


async def _retire_if_stale(factory: Any, row: _ClaimedRow) -> bool:
    """Retire the row when a newer revision was already delivered for its memory."""
    async with session_as_erasure_org(factory, row.org_id) as session:
        result = await session.execute(
            text(_RETIRE_STALE_SQL),
            {
                "id": row.row_id,
                "org_id": row.org_id,
                "memory_id": row.memory_id,
                "revision": row.revision,
                "attempts": row.attempts,
            },
        )
        return result.rowcount == 1


async def _read_refs(session: Any, row: _ClaimedRow) -> dict[str, tuple[str, ...]]:
    """Group the memory's artifact locators by store, inside the given session."""
    params = {"org_id": row.org_id, "memory_id": row.memory_id}
    grouped: dict[str, list[str]] = {}
    for store, locator in (await session.execute(text(_REFS_SQL), params)).all():
        grouped.setdefault(str(store), []).append(str(locator))
    return {store: tuple(locators) for store, locators in grouped.items()}


async def _read_erasure_state(
    factory: Any, row: _ClaimedRow
) -> tuple[dict[str, tuple[str, ...]], dict[str, str]]:
    """Read the memory's artifact locators and any receipts this revision has."""
    params = {"org_id": row.org_id, "memory_id": row.memory_id, "revision": row.revision}
    async with session_as_app_org(factory, row.org_id) as session:
        refs = await _read_refs(session, row)
        existing = {
            str(store): str(status)
            for store, status in (await session.execute(text(_RECEIPTS_SQL), params)).all()
        }
    return refs, existing


def _receipt_already_proves(proven: str | None, locators: tuple[str, ...]) -> bool:
    """Whether a receipt an earlier run wrote already settles this store.

    The durable proof is checked before the empty-locator case. A retry can
    legitimately see no locators for a store a previous run already proved (a
    store the earlier run cleared), and reporting ``not_applicable`` there would
    overwrite a ``verified`` receipt with a weaker one and drop its timestamp.

    ``not_applicable`` is kept only while there is still nothing to erase. A ref
    that appeared after that receipt is a copy that exists, so it is staged like
    any other: the weaker receipt must not hide a real copy.
    """
    if proven == "verified":
        return True
    return proven == "not_applicable" and not locators


async def _erase_store(
    erasure: _Erasure,
    target: _StoreTarget,
    existing: dict[str, str],
    job_deadline: float,
) -> _StoreOutcome:
    """Prove one store absent, or record why this run could not."""
    proven = existing.get(target.store)
    if _receipt_already_proves(proven, target.locators):
        return _StoreOutcome(store=target.store, status=proven, fresh=False)
    if not target.locators:
        # No copy of this memory was ever recorded in this store. That is a fact
        # about the memory, not a failure to reach the store — and it is only a
        # fact for a store whose producer always records a ref (RECEIPT_STORES).
        return _StoreOutcome(store=target.store, status="not_applicable")
    return await _stage_store(erasure, target, job_deadline)


def _failed_outcome(store: str, error: str) -> _StoreOutcome:
    return _StoreOutcome(store=store, status="failed", error=error)


async def _stage_store(
    erasure: _Erasure, target: _StoreTarget, job_deadline: float
) -> _StoreOutcome:
    """Stage one store inside the smaller of its own budget and the job's."""
    budget = min(
        float(erasure.settings.lifecycle_erasure_store_timeout_seconds),
        job_deadline - time.monotonic(),
    )
    if budget <= 0:
        return _failed_outcome(target.store, "job_deadline_exceeded")
    try:
        await asyncio.wait_for(
            _stage(target, erasure, time.monotonic() + budget), timeout=budget
        )
    except TimeoutError:
        return _failed_outcome(target.store, "store_timeout")
    except (PermanentErasureFailure, ValueError) as exc:
        logger.warning(
            "memory erasure store rejected its locator store=%s org_id=%s memory_id=%s revision=%s",
            target.store,
            erasure.row.org_id,
            erasure.row.memory_id,
            erasure.row.revision,
            exc_info=True,
        )
        return replace(_failed_outcome(target.store, _error_reason(exc)), permanent=True)
    except Exception as exc:
        logger.warning(
            "memory erasure store failed store=%s org_id=%s memory_id=%s revision=%s",
            target.store,
            erasure.row.org_id,
            erasure.row.memory_id,
            erasure.row.revision,
            exc_info=True,
        )
        return _failed_outcome(target.store, _error_reason(exc))
    return _StoreOutcome(store=target.store, status="verified")


def _error_reason(exc: BaseException) -> str:
    """Short, content-free reason: a locator is an address, never memory text."""
    return f"{type(exc).__name__}: {exc}"[:_ERROR_MAX_CHARS]


async def _stage(target: _StoreTarget, erasure: _Erasure, deadline: float) -> None:
    """Dispatch one store stage; every branch must raise unless absence is proven."""
    stage = _STAGE_BY_STORE.get(target.store)
    if stage is None:
        # Fail closed: a store the refs name but this module cannot erase must
        # never fall through to "nothing to do" and be reported verified.
        raise RuntimeError(f"no erasure stage for store {target.store!r}")
    await stage(target.locators, erasure, deadline)


async def _stage_objectstore(
    locators: tuple[str, ...], erasure: _Erasure, deadline: float
) -> None:
    """Delete each archived object and wait until HEAD reports it gone.

    The org is passed to the object-store client, not inferred from the URI: a
    ref row is caller-written text, so a locator naming another tenant's key must
    be refused rather than honoured.
    """
    org_id = erasure.row.org_id
    for uri in locators:
        await asyncio.to_thread(
            delete_uri, uri, org_id=org_id, settings=erasure.settings
        )
    for uri in locators:
        await _wait_object_absent(uri, org_id, erasure.settings, deadline)


async def _wait_object_absent(
    uri: str, org_id: str, settings: Any, deadline: float
) -> None:
    while True:
        if not await asyncio.to_thread(
            object_exists, uri, org_id=org_id, settings=settings
        ):
            return
        if time.monotonic() >= deadline:
            raise TimeoutError("object-store object is still present after delete")
        await asyncio.sleep(0.5)


async def _stage_clickhouse(
    locators: tuple[str, ...], erasure: _Erasure, deadline: float
) -> None:
    """Delete each recorded evidence event and wait for the mutation to land."""
    if not _stores.clickhouse_configured(erasure.settings):
        # Deployed but unreachable is a failure, never "nothing to erase".
        raise RuntimeError("clickhouse is unreachable (no CLICKHOUSE_DSN configured)")
    for event_id in locators:
        await _stores.delete_clickhouse_event(
            erasure.settings,
            org_id=erasure.row.org_id,
            event_id=event_id,
            deadline=deadline,
        )


def _session_event_id(locator: str) -> int:
    """Parse a ``session_events.id`` locator without echoing it.

    ``locator`` is caller-written text (``ibex_app`` holds INSERT on
    ``memory_artifact_refs``), so ``int(locator)`` would put the raw value into a
    ``ValueError`` message, and that message is written to the receipt's ``error``
    column and to the log. The failure is fixed text for the same reason.
    """
    if not (locator.isascii() and locator.isdigit()):
        raise PermanentErasureFailure("session_event locator is not a row id")
    return int(locator)


async def _stage_session_events(
    locators: tuple[str, ...], erasure: _Erasure, deadline: float
) -> None:
    """Delete each recorded capture event row and confirm it is gone.

    ``ibex_app`` holds no DELETE on ``session_events``: that table is the
    append-only audit trail, and the request-path identity must not be able to
    remove an event without a forget, a receipt and a legal-hold check. The verb
    belongs to ``ibex_purge`` (000064), so this one stage borrows that identity
    for the row's own org — the same fence, a narrower verb.
    """
    del deadline  # the caller's wait_for is the budget for a synchronous delete
    event_ids = [_session_event_id(locator) for locator in locators]
    params = [
        {"org_id": erasure.row.org_id, "event_id": event_id} for event_id in event_ids
    ]
    async with session_as_purge_org(erasure.factory, erasure.row.org_id) as session:
        for bound in params:
            await session.execute(text(_DELETE_SESSION_EVENT_SQL), bound)
        for bound in params:
            if await session.scalar(text(_COUNT_SESSION_EVENT_SQL), bound):
                raise RuntimeError("session_event row is still present after delete")


async def _stage_cache(
    locators: tuple[str, ...], erasure: _Erasure, deadline: float
) -> None:
    """Delete each cached memory object and wait until EXISTS reports it gone.

    The object entry carries the memory's ``content``; this is the store whose
    stale copy is the disclosure. DEL is idempotent, so a retry after a partial
    failure and a redelivery of the same revision are both safe.
    """
    client = _redis_client(erasure.settings)
    try:
        keys = [
            _cache_key("cache", locator, org_id=erasure.row.org_id)
            for locator in locators
        ]
        await client.delete(*keys)
        await _wait_cache_keys_absent(client, keys, deadline, "cache entry")
    finally:
        await client.aclose()


async def _stage_cache_hot(
    locators: tuple[str, ...], erasure: _Erasure, deadline: float
) -> None:
    """Remove this memory's member from each hot sorted set, then confirm it.

    ZREM of one member, never DEL of the key: the key belongs to the agent and
    holds every hot memory's score. Deleting it would erase live state for
    memories this forget has nothing to do with.
    """
    client = _redis_client(erasure.settings)
    member = erasure.row.memory_id
    try:
        keys = [
            _cache_key("cache_hot", locator, org_id=erasure.row.org_id)
            for locator in locators
        ]
        for key in keys:
            await client.zrem(key, member)
        await _wait_cache_member_absent(client, keys, member, deadline)
    finally:
        await client.aclose()


def _cache_key(store: str, locator: str, *, org_id: str) -> str:
    """Refuse a cache locator outside this store's tenant namespace.

    The message is fixed and never echoes the locator: a ref row is
    caller-written, so the value is attacker-influenced and it reaches both the
    receipt's ``error`` column and the worker log.
    """
    if not org_id:
        raise PermanentErasureFailure("tenant id required for cache access")
    prefix = f"{org_id}:{_CACHE_NAMESPACES[store]}:"
    if not locator.startswith(prefix):
        raise PermanentErasureFailure("cache locator is outside the tenant namespace")
    return locator


def _redis_client(settings: Any) -> Any:
    """An async Redis client for the erasure stage, or a fail-closed refusal.

    A ref that names a cache store while this deployment has no Redis URL is a
    deployment that cannot prove the store: reporting ``verified`` would be a
    claim nobody checked, so the stage raises and the receipt says ``failed``.
    """
    redis_url = getattr(settings, "redis_url", None)
    if not redis_url:
        raise RuntimeError("redis is unreachable (no REDIS_URL configured)")
    from redis.asyncio import Redis

    return Redis.from_url(
        redis_url, socket_connect_timeout=5.0, socket_timeout=5.0
    )


async def _wait_cache_keys_absent(
    client: Any, keys: list[str], deadline: float, what: str
) -> None:
    """Wait until no key exists, or fail rather than report a stale copy gone."""
    while await client.exists(*keys):
        if time.monotonic() >= deadline:
            raise TimeoutError(f"{what} is still present after delete")
        await asyncio.sleep(0.1)


async def _wait_cache_member_absent(
    client: Any, keys: list[str], member: str, deadline: float
) -> None:
    """Wait until no sorted set still scores this member."""
    while await _member_still_scored(client, keys, member):
        if time.monotonic() >= deadline:
            raise TimeoutError("hot cache member is still present after zrem")
        await asyncio.sleep(0.1)


async def _member_still_scored(client: Any, keys: list[str], member: str) -> bool:
    """Whether any of the sorted sets still scores ``member``."""
    for key in keys:
        if await client.zscore(key, member) is not None:
            return True
    return False


# Redis namespace each cache store may address. The namespace check is the tenant
# guard *and* the blast-radius guard: a ref is caller-written text, so a locator
# naming ``{org}:directive:...`` must be refused rather than deleted. Checking the
# namespace rather than an exact key keeps the worker independent of the memory
# service's key format while still refusing every key that is not one of this
# store's own structures.
_CACHE_NAMESPACES = {"cache": "memory", "cache_hot": "hot_memories"}

# Store name to stage. A store missing here fails closed rather than silently
# reporting absence; ``test_lifecycle_erasure_contract`` pins the key set to
# ``RECEIPT_STORES``.
_STAGE_BY_STORE = {
    "objectstore": _stage_objectstore,
    "clickhouse": _stage_clickhouse,
    "session_event": _stage_session_events,
    "cache": _stage_cache,
    "cache_hot": _stage_cache_hot,
}


async def _settle(
    erasure: _Erasure,
    outcomes: list[_StoreOutcome],
    staged: dict[str, tuple[str, ...]],
    rng: Callable[[], float] = random.random,
) -> str:
    """Fence the claim, re-check the stores, then write receipts and settle.

    Ordering is load-bearing. The outbox row is locked and validated against the
    attempt this run claimed *before* any receipt is written, so a worker whose
    lease expired cannot overwrite a newer worker's proof. The refs are then
    re-read under that lock, so a copy that appeared between the first read and
    this point cannot be certified by a ``verified`` receipt the run did not earn.
    """
    async with session_as_erasure_org(erasure.factory, erasure.row.org_id) as session:
        if not await _claim_still_held(session, erasure.row):
            logger.warning(
                "memory erasure settle skipped: claim superseded row_id=%s org_id=%s "
                "memory_id=%s revision=%s",
                erasure.row.row_id,
                erasure.row.org_id,
                erasure.row.memory_id,
                erasure.row.revision,
            )
            return "retired"
        checked = await _recheck_outcomes(session, erasure, outcomes, staged)
        state = _outbox_state(checked, erasure.row)
        await _apply_outbox_state(session, erasure.row, state, rng)
        await _upsert_fresh_receipts(session, erasure, checked)
    _record_outcome_metrics(checked, state)
    return state


def _outbox_state(outcomes: list[_StoreOutcome], row: _ClaimedRow) -> str:
    """The outbox state these outcomes earn, before any retry is scheduled.

    ``complete`` only when every store is proved. A locator that cannot succeed
    on retry, or a deadline that has passed, is terminally ``failed`` so the row
    stops waking; anything else is ``partial`` and retries with backoff.
    """
    if _erasure_state(outcomes) == "complete":
        return "complete"
    if _has_permanent_failure(outcomes) or _deadline_passed(row):
        return "failed"
    return "partial"


def _has_permanent_failure(outcomes: list[_StoreOutcome]) -> bool:
    """Whether any store failed in a way the next sweep cannot fix."""
    return any(outcome.permanent for outcome in outcomes)


async def _upsert_fresh_receipts(
    session: Any, erasure: _Erasure, outcomes: list[_StoreOutcome]
) -> None:
    """Write one receipt per store this run proved; an earlier proof stands."""
    for outcome in outcomes:
        if outcome.fresh:
            await session.execute(
                text(_UPSERT_RECEIPT_SQL), _receipt_params(erasure, outcome)
            )


def _record_outcome_metrics(outcomes: list[_StoreOutcome], state: str) -> None:
    """Count the per-store and per-row outcomes of one settled erasure."""
    for outcome in outcomes:
        ERASURE_STORE.labels(store=outcome.store, status=outcome.status).inc()
    ERASURE_OUTCOME.labels(state=state).inc()


async def _claim_still_held(session: Any, row: _ClaimedRow) -> bool:
    """Lock the outbox row and confirm it is still the attempt this run claimed."""
    params = {"id": row.row_id, "org_id": row.org_id, "attempts": row.attempts}
    result = await session.execute(text(_CLAIM_STILL_HELD_SQL), params)
    return result.first() is not None


async def _recheck_outcomes(
    session: Any,
    erasure: _Erasure,
    outcomes: list[_StoreOutcome],
    staged: dict[str, tuple[str, ...]],
) -> list[_StoreOutcome]:
    """Re-read the refs under the claim fence before any receipt is written."""
    current = await _read_refs(session, erasure.row)
    checked: list[_StoreOutcome] = []
    for outcome in outcomes:
        checked.append(
            await _recheck_outcome(
                erasure,
                outcome,
                staged.get(outcome.store, ()),
                current.get(outcome.store, ()),
            )
        )
    return checked


async def _recheck_outcome(
    erasure: _Erasure,
    outcome: _StoreOutcome,
    staged_locators: tuple[str, ...],
    current_locators: tuple[str, ...],
) -> _StoreOutcome:
    """Downgrade a store whose proof no longer covers what is actually there."""
    if outcome.status not in SATISFIED_RECEIPT_STATUSES:
        return outcome
    if current_locators != staged_locators:
        return _failed_outcome(outcome.store, "artifact refs changed during erasure")
    if outcome.store != "objectstore":
        return outcome
    try:
        reappeared = await _object_reappeared(erasure, staged_locators)
    except Exception:
        logger.warning(
            "memory erasure object-store re-check failed org_id=%s memory_id=%s revision=%s",
            erasure.row.org_id,
            erasure.row.memory_id,
            erasure.row.revision,
            exc_info=True,
        )
        return _failed_outcome(outcome.store, "object-store re-check failed")
    if reappeared:
        return _failed_outcome(outcome.store, "object reappeared after delete")
    return outcome


async def _object_reappeared(erasure: _Erasure, locators: tuple[str, ...]) -> bool:
    """Whether HEAD now reports any object this run had just proved absent."""
    for uri in locators:
        if await asyncio.to_thread(
            object_exists, uri, org_id=erasure.row.org_id, settings=erasure.settings
        ):
            return True
    return False


async def _apply_outbox_state(
    session: Any, row: _ClaimedRow, state: str, rng: Callable[[], float]
) -> None:
    """Move the locked outbox row to its next state."""
    params: dict[str, Any] = {
        "id": row.row_id,
        "org_id": row.org_id,
        "attempts": row.attempts,
    }
    if state == "complete":
        await session.execute(text(_COMPLETE_SQL), params)
        return
    if state == "failed":
        await session.execute(text(_FAIL_SQL), params)
        return
    params["delay_seconds"] = _backoff_seconds(row.attempts, rng)
    await session.execute(text(_RETRY_SQL), params)


def _erasure_state(outcomes: list[_StoreOutcome]) -> str:
    """``complete`` only when every store is verified or not applicable."""
    if all(outcome.status in SATISFIED_RECEIPT_STATUSES for outcome in outcomes):
        return "complete"
    return "partial"


def _deadline_passed(row: _ClaimedRow) -> bool:
    return row.deadline is not None and row.deadline <= datetime.now(tz=UTC)


def _backoff_seconds(attempts: int, rng: Callable[[], float] = random.random) -> int:
    """Capped exponential retry delay with bounded, injected jitter.

    ``rng`` is a callable returning ``[0, 1)``; the default is
    ``random.random`` and the tests inject a deterministic source. The jitter
    stays inside ``_RETRY_CAP_SECONDS`` so two erasures hitting the same outage
    do not wake at the same instant.
    """
    exponent = max(attempts - 1, 0)
    base = min(_RETRY_BASE_SECONDS * (2**exponent), _RETRY_CAP_SECONDS)
    jitter = _RETRY_JITTER_FRACTION * (2.0 * rng() - 1.0)
    return max(0, min(_RETRY_CAP_SECONDS, int(base * (1.0 + jitter))))


def _receipt_params(erasure: _Erasure, outcome: _StoreOutcome) -> dict[str, Any]:
    row = erasure.row
    return {
        "org_id": row.org_id,
        "memory_id": row.memory_id,
        "revision": row.revision,
        "store": outcome.store,
        "status": outcome.status,
        "idempotency_key": (
            f"erase:{row.org_id}:{row.memory_id}:{row.revision}:{outcome.store}"
        ),
        "error": outcome.error,
    }


__all__ = [
    "ERASURE_EVENT_TYPES",
    "ERASURE_OUTCOME",
    "ERASURE_STORE",
    "RECEIPT_STORES",
    "SATISFIED_RECEIPT_STATUSES",
    "PermanentErasureFailure",
    "configure_erasure_task_limits",
    "erase_memory",
]
