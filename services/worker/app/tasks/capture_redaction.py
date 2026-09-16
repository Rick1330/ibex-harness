"""Async capture-policy redaction / archive task (never on proxy hot path)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text

from app.celery_app import celery_app
from app.config import get_settings
from app.db import create_engine, create_session_factory, session_as_service_org
from app.tasks.base import IbexTask

logger = logging.getLogger(__name__)

TASK_APPLY_CAPTURE_REDACTION = "ibex.privacy.apply_capture_redaction"
_DEFAULT_MODE = "metadata_only"
_STRIP_KEYS = frozenset({"raw", "content", "prompt"})


@dataclass(frozen=True)
class _CaptureJob:
    """Bundles Celery kwargs so helpers stay under CodeScene arity limits."""

    org_id: str
    event_id: str | None = None
    agent_id: str | None = None
    payload: dict[str, Any] | None = None


@celery_app.task(
    bind=True,
    base=IbexTask,
    name=TASK_APPLY_CAPTURE_REDACTION,
    queue="maintenance",
    soft_time_limit=120,
    time_limit=180,
)
def apply_capture_redaction(self: IbexTask, **kwargs: Any) -> dict[str, str]:
    """Load org capture policy and redact or queue archive for eligible events.

    Keyword args: ``org_id`` (required), ``event_id``, ``agent_id``, ``payload``.
    """
    del self
    import asyncio

    return asyncio.run(_run(_parse_job(kwargs)))


def _parse_job(kwargs: dict[str, Any]) -> _CaptureJob:
    org_id = kwargs.get("org_id")
    if not org_id or not isinstance(org_id, str):
        raise ValueError("org_id is required")
    payload = kwargs.get("payload")
    return _CaptureJob(
        org_id=org_id,
        event_id=kwargs.get("event_id"),
        agent_id=kwargs.get("agent_id"),
        payload=payload if isinstance(payload, dict) else {},
    )


async def _run(job: _CaptureJob) -> dict[str, str]:
    settings = get_settings()
    if not settings.database_url:
        raise ValueError("database_url is required")
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with session_as_service_org(factory, job.org_id) as session:
            parsed_agent = UUID(job.agent_id) if job.agent_id else None
            mode = await resolve_capture_mode(session, org_id=job.org_id, agent_id=parsed_agent)
            return await _apply_mode(session, settings, mode, job)
    finally:
        await engine.dispose()


async def _apply_mode(session, settings: Any, mode: str, job: _CaptureJob) -> dict[str, str]:
    payload = job.payload or {}
    if mode == "none":
        return {"status": "skipped", "mode": mode}
    if mode == "metadata_only":
        return {"status": "redacted", "mode": mode}
    if mode == "redacted":
        filtered = {k: v for k, v in payload.items() if k not in _STRIP_KEYS}
        await _persist_redacted(session, settings, job, filtered)
        return {"status": "redacted", "mode": mode, "event_id": job.event_id or ""}
    if payload:
        await _archive_payload(session, settings, job, payload)
    return {"status": "archived", "mode": mode, "event_id": job.event_id or ""}


async def resolve_capture_mode(session, *, org_id: str, agent_id: UUID | None) -> str:
    """Priority load: agent-specific then org-default; reader default metadata_only."""
    result = await session.execute(
        text(
            """
            SELECT mode FROM ibex_core.org_capture_policies
            WHERE org_id = CAST(:org_id AS uuid)
              AND (
                    (:agent_id IS NULL AND agent_id IS NULL)
                 OR (agent_id = CAST(:agent_id AS uuid))
                 OR (agent_id IS NULL)
              )
            ORDER BY
                CASE WHEN agent_id IS NOT NULL THEN 0 ELSE 1 END,
                priority ASC
            LIMIT 1
            """
        ),
        {
            "org_id": org_id,
            "agent_id": str(agent_id) if agent_id else None,
        },
    )
    row = result.first()
    if row is None:
        return _DEFAULT_MODE
    return str(row[0])


async def _persist_redacted(session, settings: Any, job: _CaptureJob, filtered: dict[str, Any]) -> None:
    if not job.event_id:
        return
    await session.execute(
        text(
            """
            UPDATE ibex_core.session_events
            SET data = CAST(:data AS jsonb)
            WHERE id = CAST(:event_id AS bigint)
              AND org_id = CAST(:org_id AS uuid)
            """
        ),
        {
            "event_id": job.event_id,
            "org_id": job.org_id,
            "data": json.dumps(filtered),
        },
    )
    try:
        uri = _put_archive_blob(settings, job, filtered, "redacted")
    except RuntimeError as exc:
        if "S3_ENDPOINT" in str(exc) or "MASTER_KEY" in str(exc):
            return
        raise
    await _set_archived_to(session, job, uri)


async def _archive_payload(session, settings: Any, job: _CaptureJob, payload: dict[str, Any]) -> None:
    uri = _put_archive_blob(settings, job, payload, "full")
    if job.event_id:
        await _set_archived_to(session, job, uri)


async def _set_archived_to(session, job: _CaptureJob, uri: str) -> None:
    await session.execute(
        text(
            """
            UPDATE ibex_core.session_events
            SET archived_to = :uri
            WHERE id = CAST(:event_id AS bigint)
              AND org_id = CAST(:org_id AS uuid)
            """
        ),
        {"event_id": job.event_id, "org_id": job.org_id, "uri": uri},
    )


def _put_archive_blob(settings: Any, job: _CaptureJob, payload: dict[str, Any], kind: str) -> str:
    from app.objectstore_client import put_encrypted_json

    key = f"{job.org_id}/capture/{kind}/{job.event_id or 'anon'}.json"
    body = json.dumps(
        {"org_id": job.org_id, "event_id": job.event_id, "payload": payload}
    ).encode()
    return put_encrypted_json(key, body, settings=settings)
