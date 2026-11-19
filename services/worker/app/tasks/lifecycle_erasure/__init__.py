"""Memory-lifecycle erasure consumer: prove a forgotten memory is gone everywhere.

The forget path (``services/memory/app/lifecycle.py``) tombstones the memory row
and writes one ``memory_lifecycle_outbox`` row in the same transaction. This
package is the consumer: it claims the row, erases every copy outside
PostgreSQL, writes one receipt per store, and settles the row.

Layout, by responsibility:

* ``constants`` — the store vocabulary, budgets and retry constants;
* ``sql`` — every statement, all with the explicit org predicate;
* ``model`` — the claimed row, the dependencies, the store targets/outcomes;
* ``decisions`` — the pure rules (what is proved, what is a retry, what is
  ``complete``, what is ``not_applicable``);
* ``staging`` — the per-store operations, including the cache stages and the
  forgotten marker that stops a delayed write from recreating an erased object;
* ``sweep`` — claim, retire, read state, derive a missing cache address, stage,
  fence and settle;
* ``metrics`` — the Prometheus counters.

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
  "this memory has no copy in that store" and nothing else).
* A store already proven for this revision is not re-staged: the first proof
  stands and its ``verified_absent_at`` is not overwritten by a retry.
* A row whose ``revision`` is lower than one already delivered for the same
  memory is retired, not erased: the newer revision describes the same memory's
  end state, so this row has nothing left to prove.
* ``erasure_state`` becomes ``complete`` only when every receipt is ``verified``
  or ``not_applicable``; otherwise ``partial`` with exponential backoff, until
  ``erasure_deadline`` passes and the row is terminally ``failed``.
* A cache row with no recorded ref is not ``not_applicable``: the keys are
  derivable from ``(org, agent, memory)``, so this consumer derives them and
  erases what the ref could not point at. An unconfigured Redis is ``failed``.

Tenant boundary: discovery runs through the ``SECURITY DEFINER`` claim function
(the outbox is RLS-scoped, so a sweep with no tenant selected would see nothing)
and returns identifiers only. Every statement after the claim runs through
``session_as_app_org`` — ``ibex_app`` plus ``app.current_org_id`` — so RLS fences
the row's own org. The single exception is the ``session_events`` DELETE, which
runs through ``session_as_purge_org`` because ``ibex_app`` holds no DELETE on an
append-only audit trail. The ClickHouse mutation carries the org predicate
explicitly because ClickHouse has no RLS.

Deadlines: ``lifecycle_erasure_store_timeout_seconds`` (120 s) per store and
``lifecycle_erasure_job_timeout_seconds`` (900 s) for the whole row. Both are
hard stops that become a ``failed`` receipt rather than a longer wait. The Celery
task limits are derived from the job budget plus settlement headroom, so a legal
longer budget is not killed by a fixed task limit before its own deadline.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.celery_app import celery_app
from app.config import get_settings
from app.task_names import TASK_LIFECYCLE_ERASE_MEMORY
from app.tasks.base import IbexTask

# Submodules stay reachable as attributes (``lifecycle_erasure.sweep``) so a
# test can drive the seam it is exercising without importing a private module
# path. The public and private names below are re-exported for the same reason:
# callers keep importing from this package.
from . import constants, decisions, metrics, model, sql, staging, sweep  # noqa: F401
from .constants import (  # noqa: F401
    _CACHE_FORGOTTEN_NAMESPACE,
    _CACHE_FORGOTTEN_TTL_SECONDS,
    _CACHE_NAMESPACES,
    _CLAIM_BATCH,
    _ERASURE_KILL_GRACE_SECONDS,
    _ERASURE_SETTLEMENT_HEADROOM_SECONDS,
    _ERROR_MAX_CHARS,
    _RETRY_BASE_SECONDS,
    _RETRY_CAP_SECONDS,
    _RETRY_JITTER_FRACTION,
    CACHE_STORES,
    ERASURE_EVENT_TYPES,
    RECEIPT_STORES,
    SATISFIED_RECEIPT_STATUSES,
    _task_limits,
)
from .decisions import (  # noqa: F401
    _backoff_seconds,
    _deadline_passed,
    _erasure_state,
    _error_reason,
    _failed_outcome,
    _failed_target,
    _has_permanent_failure,
    _outbox_state,
    _receipt_already_proves,
    _receipt_params,
    _session_event_id,
    _stores_to_stage,
)
from .metrics import ERASURE_OUTCOME, ERASURE_STORE
from .model import (  # noqa: F401
    PermanentErasureFailure,
    _ClaimedRow,
    _Erasure,
    _StoreOutcome,
    _StoreTarget,
)
from .sql import (  # noqa: F401
    _AGENT_ID_SQL,
    _CLAIM_SQL,
    _CLAIM_STILL_HELD_SQL,
    _COMPLETE_SQL,
    _COUNT_SESSION_EVENT_SQL,
    _DELETE_SESSION_EVENT_SQL,
    _FAIL_SQL,
    _RECEIPTS_SQL,
    _REFS_SQL,
    _RETIRE_STALE_SQL,
    _RETRY_SQL,
    _UPSERT_RECEIPT_SQL,
)
from .staging import (  # noqa: F401
    _STAGE_BY_STORE,
    _cache_key,
    _forgotten_key,
    _member_still_scored,
    _redis_client,
    _stage,
    _stage_cache,
    _stage_cache_hot,
    _stage_clickhouse,
    _stage_objectstore,
    _stage_session_events,
    _wait_cache_keys_absent,
    _wait_cache_member_absent,
    _wait_object_absent,
    delete_uri,
    object_exists,
)
from .sweep import (  # noqa: F401
    _apply_outbox_state,
    _claim_one,
    _claim_still_held,
    _derived_cache_locators,
    _erase_row,
    _erase_store,
    _object_reappeared,
    _read_agent_id,
    _read_erasure_state,
    _read_refs,
    _recheck_outcome,
    _recheck_outcomes,
    _record_outcome_metrics,
    _retire_if_stale,
    _run_sweep,
    _settle,
    _stage_store,
    _staged_locators,
    _store_targets,
    _upsert_fresh_receipts,
    create_engine,
    create_session_factory,
)

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


__all__ = [
    "CACHE_STORES",
    "ERASURE_EVENT_TYPES",
    "ERASURE_OUTCOME",
    "ERASURE_STORE",
    "RECEIPT_STORES",
    "SATISFIED_RECEIPT_STATUSES",
    "PermanentErasureFailure",
    "configure_erasure_task_limits",
    "erase_memory",
]
