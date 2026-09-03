"""Batched session-close memory extraction (m3.5.B.2)."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from app.celery_app import celery_app
from app.config import Settings, get_settings
from app.db import create_engine, create_session_factory
from app.extraction.batch import BatchJob, BatchRunResult, parse_turns, run_batch_extraction
from app.extraction.factory import load_active_extraction_provider
from app.extraction.memory_writer import HttpMemoryWriter, MemoryHttpConfig
from app.extraction.provider import ExtractionTransportError
from app.extraction.session_store import PostgresSessionStore, SessionStore
from app.task_context import parse_org_id
from app.task_names import TASK_EXTRACT_SESSION_MEMORIES
from app.tasks.base import IbexTask


def _parse_uuid(raw: object, field: str) -> UUID:
    if raw is None:
        raise ValueError(f"{field} is required")
    try:
        return UUID(str(raw))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a UUID") from exc


def _memory_writer(settings: Settings) -> HttpMemoryWriter:
    writer_token = settings.memory_api_token
    if not settings.memory_base_url or writer_token is None:
        raise ValueError("memory_base_url and memory_api_token are required")
    token = writer_token.get_secret_value()
    if not token.strip():
        raise ValueError("memory_api_token is required")
    return HttpMemoryWriter(
        MemoryHttpConfig(base_url=settings.memory_base_url, token=token)
    )


def _optional_session_store(
    settings: Settings,
) -> tuple[SessionStore | None, AsyncEngine | None]:
    if not settings.database_url:
        return None, None
    engine = create_engine(settings)
    return PostgresSessionStore(create_session_factory(engine)), engine


def _dispose_engine(engine: AsyncEngine | None) -> None:
    if engine is None:
        return
    asyncio.run(engine.dispose())


def _task_payload(result: BatchRunResult) -> dict[str, Any]:
    return {
        "status": "ok" if result.skipped is None else "skipped",
        "memories_written": result.memories_written,
        "turns_processed": result.turns_processed,
        "skipped": result.skipped,
    }


@celery_app.task(
    bind=True,
    base=IbexTask,
    name=TASK_EXTRACT_SESSION_MEMORIES,
    queue="extraction",
    autoretry_for=(ExtractionTransportError,),
    dont_autoretry_for=(ValueError,),
    soft_time_limit=120,
    time_limit=180,
)
def extract_session_memories(self: IbexTask, **kwargs: Any) -> dict[str, Any]:
    """Extract memories for a completed session from payload turns."""
    del self
    org_id = parse_org_id(kwargs)
    if org_id is None:
        raise ValueError("org_id is required")
    agent_id = _parse_uuid(kwargs.get("agent_id"), "agent_id")
    session_id = _parse_uuid(kwargs.get("session_id"), "session_id")
    turns = parse_turns(kwargs.get("turns"))
    settings = get_settings()
    writer = _memory_writer(settings)
    session_store, engine = _optional_session_store(settings)
    try:
        result = run_batch_extraction(
            BatchJob(
                org_id=org_id,
                agent_id=agent_id,
                session_id=session_id,
                turns=turns,
                provider=load_active_extraction_provider(),
                memory_writer=writer,
                clickhouse_dsn=settings.clickhouse_dsn,
                session_store=session_store,
            )
        )
        return _task_payload(result)
    finally:
        writer.close()
        _dispose_engine(engine)
