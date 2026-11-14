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
from sqlalchemy.exc import SQLAlchemyError

from app.exceptions import ConflictError, MemoryNotFoundError
from app.lifecycle import ForgetMemory, forget_memory_session

logger = logging.getLogger(__name__)


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
