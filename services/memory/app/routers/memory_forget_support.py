"""Forget (tombstone) orchestration for the memory write routes.

Forget is a destructive lifecycle operation: it tombstones the row inside its
own transaction and then invalidates the caches derived from it. Database and
lifecycle failures are mapped to stable HTTP envelopes here so the route only
sequences the calls.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import session_with_org
from app.exceptions import ConflictError, MemoryNotFoundError
from app.lifecycle import ForgetMemory, forget_memory_session
from app.schemas.memories import ErasureStatus, ErasureStores

logger = logging.getLogger(__name__)

#: The stores whose proof ``ibex.worker.lifecycle.erase_memory`` can produce. One
#: receipt per store is written by that consumer; a store with no receipt yet is
#: reported as ``pending`` rather than assumed clean.
#:
#: ClickHouse is not here: no producer records a per-memory ClickHouse locator, so
#: the consumer cannot prove that store, and a receipt for it would be a claim
#: nobody made. It is erased by the org-deletion saga instead, which proves
#: absence org-wide. Reporting it as ``not_applicable`` would certify an erasure
#: that never ran.
ERASURE_STORES: tuple[str, ...] = ("objectstore", "session_event")

_OUTBOX_STATE_SQL = """
SELECT erasure_state
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


async def forget_memory_with_error_mapping(
    *,
    session_factory: Any,
    command: ForgetMemory,
) -> int:
    """Tombstone a memory, mapping lifecycle and database failures to HTTP."""
    try:
        async with session_factory() as session, session.begin():
            return await forget_memory_session(session, command)
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
    org_id: UUID,
    agent_id: UUID,
    memory_id: UUID,
) -> None:
    """Best-effort cache invalidation after a committed forget."""
    if cache_writer is None:
        return
    try:
        await cache_writer.forget_memory(org_id=org_id, agent_id=agent_id, memory_id=memory_id)
    except Exception:
        logger.warning(  # NOSONAR pythonsecurity:S5145 - UUID hex is hex-only, not free text
            "memory cache invalidation failed after committed forget org_id=%s memory_id=%s",
            org_id.hex,
            memory_id.hex,
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
    from the latter, so the two cannot disagree. Reading them is deliberately
    separate from the forget transaction: erasure happens after it commits, and
    this route must not report ``complete`` for work that has not run.

    A read failure degrades to ``pending`` rather than failing the request. The
    tombstone is already committed, so a 503 here would invite a retry that the
    lifecycle fence answers with 409 for a memory that is in fact forgotten;
    "no proof recorded yet" is both true and actionable.
    """
    params = {"org_id": org_id, "memory_id": memory_id, "revision": revision}
    try:
        async with session_with_org(session_factory, str(org_id)) as session:
            job_state = await session.scalar(text(_OUTBOX_STATE_SQL), params)
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
    return _erasure_status(job_state, rows)


#: Values the response contract accepts. A row can only hold these (CHECK
#: constraints in 000074/000073), but a mapping step that raised on an
#: unexpected value would turn a committed forget into a 500, so anything else
#: degrades to "no proof yet" instead.
_JOB_STATES = frozenset({"pending", "partial", "complete", "failed"})
_STORE_STATES = frozenset({"pending", "verified", "failed", "not_applicable"})


def _erasure_status(job_state: str | None, rows: Any) -> ErasureStatus:
    """Map the outbox state and the receipts onto the response contract."""
    statuses = {str(store): str(status) for store, status in rows}
    stores = ErasureStores(
        **{
            store: (
                statuses[store] if statuses.get(store) in _STORE_STATES else "pending"
            )
            for store in ERASURE_STORES
        }
    )
    state = job_state if job_state in _JOB_STATES else "pending"
    return ErasureStatus(state=state, stores=stores)
