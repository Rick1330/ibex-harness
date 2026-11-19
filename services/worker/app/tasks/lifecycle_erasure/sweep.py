"""The erasure sweep: claim a row, stage every store, settle it honestly.

Ordering is load-bearing and easy to get wrong:

* only erasure events are consumed (the claim function enforces the set);
* a row whose revision is lower than one already delivered is retired, not
  erased — the newer revision describes the same memory's end state;
* a store already proven for this revision is not re-staged, and its
  ``verified_absent_at`` is not overwritten by a retry;
* the outbox row is locked and validated against the attempt this run claimed
  *before* any receipt is written, and the refs are re-read under that lock, so
  a copy that appeared in between cannot be certified by a receipt the run did
  not earn;
* ``erasure_state`` becomes ``complete`` only when every receipt is ``verified``
  or ``not_applicable``; otherwise ``partial`` with backoff, until the deadline
  passes and the row is terminally ``failed``.

The cache stores are staged even without a ref when their keys are derivable
from the row, because an absent ref means "not recorded", never "proved absent".
A ``purged`` row could not derive its hot key at all until the organization saga
started recording that address before it deletes the memory row; a row from a
saga that predates that insert has no address and cannot be certified by the
org-wide receipt, which proves a delete ran rather than that no write followed.

A stored ``verified`` receipt is not proof forever for the object store. The
archive key is derived from the row and nothing fences a late re-archive, so a
HEAD that finds the object back restages it instead of trusting the receipt.
That HEAD runs before the run's store budgets, so it is capped: a slow object
store that never answers may cost one bounded check, not the row's remaining
time.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import text

from app.config import get_settings
from app.db import (
    create_engine,
    create_session_factory,
    session_as_app_org,
    session_as_erasure_org,
    session_unpinned,
)
from app.objectstore_client import object_exists

from .constants import (
    _CACHE_NAMESPACES,
    _CLAIM_BATCH,
    CACHE_STORES,
    SATISFIED_RECEIPT_STATUSES,
)
from .decisions import (
    _backoff_seconds,
    _error_reason,
    _outbox_state,
    _receipt_already_proves,
    _receipt_params,
    _stores_to_stage,
    _underivable_outcome,
)
from .metrics import ERASURE_OUTCOME, ERASURE_STORE
from .model import (
    PermanentErasureFailure,
    _ClaimedRow,
    _Erasure,
    _ErasureState,
    _StoreOutcome,
    _StoreTarget,
)
from .sql import (
    _AGENT_ID_SQL,
    _CLAIM_SQL,
    _CLAIM_STILL_HELD_SQL,
    _COMPLETE_SQL,
    _FAIL_SQL,
    _ORG_PURGE_SQL,
    _RECEIPTS_SQL,
    _REFS_SQL,
    _RETIRE_STALE_SQL,
    _RETRY_SQL,
    _UPSERT_RECEIPT_SQL,
)
from .staging import _stage

logger = logging.getLogger(__name__)

#: How long one proof HEAD may run. A HEAD is a liveness question about a single
#: key, not a transfer: a healthy S3/MinIO answers in milliseconds, so five
#: seconds tolerates a degraded endpoint while staying far below the 120 s store
#: budget. The proof runs before the cache stores in the same row; without this
#: cap a slow object store could consume the job budget and turn an untried
#: cache store into ``job_deadline_exceeded``.
_PROOF_HEAD_CAP_SECONDS = 5.0


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
    state = await _read_erasure_state(factory, row)
    erasure = _Erasure(
        row=row,
        settings=settings,
        factory=factory,
        agent_id=state.agent_id,
        org_redis_purge=state.org_redis_purge,
        job_deadline=job_deadline,
    )
    targets = _store_targets(state.refs, state.agent_id, row)
    outcomes = [
        await _erase_store(erasure, target, state.receipts, job_deadline)
        for target in targets
    ]
    return await _settle(erasure, outcomes, _staged_locators(targets))


def _staged_locators(targets: tuple[_StoreTarget, ...]) -> dict[str, tuple[str, ...]]:
    """The addresses this run staged, keyed by store, for the settle re-check."""
    return {target.store: target.locators for target in targets}


def _store_targets(
    refs: dict[str, tuple[str, ...]], agent_id: str | None, row: _ClaimedRow
) -> tuple[_StoreTarget, ...]:
    """One target per store this run settles, deriving an absent cache ref.

    A recorded ref is the address. For a cache store with no ref — a row that
    predates 000078 or a forget whose request path recorded nothing — the key is
    derivable from the row, so it is derived instead of reported
    ``not_applicable``. The object key needs only ``(org, memory)``; the hot key
    also needs the memory's agent. If the memory row is gone the hot address
    cannot be derived, and the store fails rather than claiming absence it never
    checked.
    """
    targets: list[_StoreTarget] = []
    for store in _stores_to_stage(refs):
        recorded = refs.get(store, ())
        if recorded:
            targets.append(_StoreTarget(store, recorded))
            continue
        derived = _derived_cache_locators(store, agent_id, row)
        if derived is None:
            targets.append(_StoreTarget(store, (), underivable=True))
            continue
        targets.append(_StoreTarget(store, derived, derived=bool(derived)))
    return tuple(targets)


def _derived_cache_locators(
    store: str, agent_id: str | None, row: _ClaimedRow
) -> tuple[str, ...] | None:
    """The cache address a pre-ref row must still be able to reach.

    ``None`` means the store is a cache store whose key needs a value this row
    does not have; anything else is a (possibly empty) locator tuple.
    """
    if store not in CACHE_STORES:
        return ()
    if store == "cache":
        return (f"{row.org_id}:{_CACHE_NAMESPACES['cache']}:{row.memory_id}",)
    if agent_id is None:
        return None
    return (f"{row.org_id}:{_CACHE_NAMESPACES['cache_hot']}:{agent_id}",)


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


async def _read_agent_id(session: Any, row: _ClaimedRow) -> str | None:
    """The memory's agent, needed only to derive the hot cache key."""
    params = {"org_id": row.org_id, "memory_id": row.memory_id}
    found = (await session.execute(text(_AGENT_ID_SQL), params)).first()
    return str(found[0]) if found is not None else None


async def _read_erasure_state(factory: Any, row: _ClaimedRow) -> _ErasureState:
    """Read refs, receipts, the memory's agent and any org purge verdict."""
    params = {"org_id": row.org_id, "memory_id": row.memory_id, "revision": row.revision}
    async with session_as_app_org(factory, row.org_id) as session:
        refs = await _read_refs(session, row)
        receipts = {
            str(store): str(status)
            for store, status in (await session.execute(text(_RECEIPTS_SQL), params)).all()
        }
        agent_id = await _read_agent_id(session, row)
        org_redis_purge = await _read_org_purge(session, row)
    return _ErasureState(
        refs=refs,
        receipts=receipts,
        agent_id=agent_id,
        org_redis_purge=org_redis_purge,
    )


async def _read_org_purge(session: Any, row: _ClaimedRow) -> str | None:
    """The organization purge's Redis verdict, for a ``purged`` row only.

    Only a ``purged`` row needs it: the org saga deleted the memory, so its agent
    — and the hot key derived from it — is gone. Every other row keeps the
    permanent failure for an underivable address, so the query is skipped there.
    """
    if row.event_type != "purged":
        return None
    found = (
        await session.execute(text(_ORG_PURGE_SQL), {"org_id": row.org_id})
    ).first()
    return str(found[0]) if found is not None else None


async def _erase_store(
    erasure: _Erasure,
    target: _StoreTarget,
    receipts: dict[str, str],
    job_deadline: float,
) -> _StoreOutcome:
    """Prove one store absent, or record why this run could not."""
    settled = await _durable_proof(erasure, target, receipts.get(target.store))
    if settled is not None:
        return _StoreOutcome(store=target.store, status=settled, fresh=False)
    if target.underivable:
        return _underivable_outcome(erasure, target)
    if not target.locators:
        # No copy of this memory was ever recorded in this store. That is a fact
        # about the memory, not a failure to reach the store — and it is only a
        # fact for a store whose producer always records a ref (RECEIPT_STORES)
        # or whose key this run derived.
        return _StoreOutcome(store=target.store, status="not_applicable")
    return await _stage_store(erasure, target, job_deadline)


async def _durable_proof(
    erasure: _Erasure, target: _StoreTarget, proven: str | None
) -> str | None:
    """The stored receipt that still settles this store, or None to stage it.

    A stored ``verified`` receipt is not proof forever for the object store: the
    archive key is derived from ``(org, memory)`` and nothing fences a late
    re-archive, so an object that is back means the retry has to delete it again.
    The cache stores are fenced by the forgotten marker, and a new ref is caught
    by the settle re-check.

    The HEAD this issues is bounded by the job deadline, so it cannot spend the
    budget the cache stores later in the row still need; an expired check counts
    as "the object may be back" and restages the store.
    """
    if proven is None or not _receipt_already_proves(proven, target.locators):
        return None
    if await _object_returned(erasure, target):
        return None
    return proven


async def _object_returned(erasure: _Erasure, target: _StoreTarget) -> bool:
    """Whether HEAD finds an object a stored receipt had proved absent.

    Only the object store is re-checked. A HEAD that cannot answer is treated as
    "restage": the object is deleted again rather than certified on a check that
    did not happen, and DELETE is idempotent.
    """
    if target.store != "objectstore" or not target.locators:
        return False
    try:
        return await _object_reappeared(erasure, target.locators)
    except Exception:
        logger.warning(
            "memory erasure object-store proof re-check failed org_id=%s "
            "memory_id=%s revision=%s",
            erasure.row.org_id,
            erasure.row.memory_id,
            erasure.row.revision,
            exc_info=True,
        )
        return True


async def _stage_store(
    erasure: _Erasure, target: _StoreTarget, job_deadline: float
) -> _StoreOutcome:
    """Stage one store inside the smaller of its own budget and the job's."""
    budget = min(
        float(erasure.settings.lifecycle_erasure_store_timeout_seconds),
        job_deadline - time.monotonic(),
    )
    if budget <= 0:
        return _StoreOutcome(
            store=target.store, status="failed", error="job_deadline_exceeded"
        )
    try:
        await asyncio.wait_for(
            _stage(target, erasure, time.monotonic() + budget), timeout=budget
        )
    except TimeoutError:
        return _StoreOutcome(store=target.store, status="failed", error="store_timeout")
    except Exception as exc:
        logger.warning(
            "memory erasure store failed store=%s org_id=%s memory_id=%s revision=%s",
            target.store,
            erasure.row.org_id,
            erasure.row.memory_id,
            erasure.row.revision,
            exc_info=True,
        )
        return _StoreOutcome(
            store=target.store,
            status="failed",
            error=_error_reason(exc),
            permanent=_is_permanent(exc),
        )
    return _StoreOutcome(store=target.store, status="verified")


def _is_permanent(exc: BaseException) -> bool:
    """Whether the failure is a property of the locator, not a transient outage."""
    return isinstance(exc, (PermanentErasureFailure, ValueError))


async def _settle(
    erasure: _Erasure,
    outcomes: list[_StoreOutcome],
    staged: dict[str, tuple[str, ...]],
    rng: Callable[[], float] = random.random,
) -> str:
    """Fence the claim, re-check the stores, then write receipts and settle."""
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
    """Re-read the refs under the claim fence before any receipt is written.

    The current locators are recomputed through the same derivation the stage
    used, so a store this run addressed from a derived key still matches when no
    ref appeared. A ref that *did* appear means the copy has an address this run
    did not erase, so the proof does not cover it.
    """
    current = await _read_refs(session, erasure.row)
    current_targets = _staged_locators(
        _store_targets(current, erasure.agent_id, erasure.row)
    )
    checked: list[_StoreOutcome] = []
    for outcome in outcomes:
        checked.append(
            await _recheck_outcome(
                erasure,
                outcome,
                staged.get(outcome.store, ()),
                current_targets.get(outcome.store, ()),
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
        return _StoreOutcome(
            store=outcome.store,
            status="failed",
            error="artifact refs changed during erasure",
        )
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
        return _StoreOutcome(
            store=outcome.store, status="failed", error="object-store re-check failed"
        )
    if reappeared:
        return _StoreOutcome(
            store=outcome.store, status="failed", error="object reappeared after delete"
        )
    return outcome


async def _object_reappeared(erasure: _Erasure, locators: tuple[str, ...]) -> bool:
    """Whether HEAD now reports any object this run had just proved absent.

    Each check is bounded, and the loop stops once the budget is gone instead of
    starting a HEAD that cannot finish. A check that expires raises, exactly as
    an unanswered one does, so the proof path restages and the settle re-check
    refuses to certify — neither reads a timeout as absence.
    """
    for uri in locators:
        if await _head_object(uri, erasure):
            return True
    return False


def _proof_head_budget(erasure: _Erasure) -> float:
    """How long one proof HEAD may run: the per-call cap, cut by the job deadline."""
    remaining = _PROOF_HEAD_CAP_SECONDS
    if erasure.job_deadline is not None:
        remaining = min(remaining, erasure.job_deadline - time.monotonic())
    return remaining


async def _head_object(uri: str, erasure: _Erasure) -> bool:
    """HEAD one locator inside the proof budget; raise ``TimeoutError`` if it expires.

    The timeout is the same answer as an unreachable store: absence was not
    proved. Deleting again is idempotent, so the caller restages instead of
    treating the silence as a cleared object.
    """
    budget = _proof_head_budget(erasure)
    if budget <= 0:
        raise TimeoutError("object-store proof budget exhausted")
    return await asyncio.wait_for(
        asyncio.to_thread(
            object_exists,
            uri,
            org_id=erasure.row.org_id,
            settings=erasure.settings,
        ),
        timeout=budget,
    )


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
