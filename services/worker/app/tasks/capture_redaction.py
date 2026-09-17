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


@dataclass
class _RedactCtx:
    """Session + settings + upload ledger for one redaction run."""

    session: Any
    settings: Any
    job: _CaptureJob
    uploaded: list[str]


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
    if payload is not None and not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    return _CaptureJob(
        org_id=org_id,
        event_id=kwargs.get("event_id"),
        agent_id=kwargs.get("agent_id"),
        payload=payload,
    )


async def _run(job: _CaptureJob) -> dict[str, str]:
    settings = get_settings()
    if not settings.database_url:
        raise ValueError("database_url is required")
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    uploaded: list[str] = []
    try:
        async with session_as_service_org(factory, job.org_id) as session:
            parsed_agent = UUID(job.agent_id) if job.agent_id else None
            mode = await resolve_capture_mode(session, org_id=job.org_id, agent_id=parsed_agent)
            ctx = _RedactCtx(session=session, settings=settings, job=job, uploaded=uploaded)
            return await _apply_mode(ctx, mode)
    except Exception:
        for uri in uploaded:
            _compensate_upload(uri, settings)
        raise
    finally:
        await engine.dispose()


async def _apply_mode(ctx: _RedactCtx, mode: str) -> dict[str, str]:
    if mode == "none":
        return {"status": "skipped", "mode": mode}
    if mode == "metadata_only":
        return {"status": "redacted", "mode": mode}
    if mode == "redacted":
        return await _mode_redacted(ctx)
    return await _mode_archive(ctx, mode)


async def _mode_redacted(ctx: _RedactCtx) -> dict[str, str]:
    payload = ctx.job.payload or {}
    filtered = {k: v for k, v in payload.items() if k not in _STRIP_KEYS}
    await _persist_redacted(ctx, filtered)
    return {"status": "redacted", "mode": "redacted", "event_id": ctx.job.event_id or ""}


async def _mode_archive(ctx: _RedactCtx, mode: str) -> dict[str, str]:
    payload = ctx.job.payload or {}
    if payload:
        await _archive_payload(ctx, payload)
    return {"status": "archived", "mode": mode, "event_id": ctx.job.event_id or ""}


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


async def _persist_redacted(ctx: _RedactCtx, filtered: dict[str, Any]) -> None:
    job = ctx.job
    if not job.event_id:
        return
    await ctx.session.execute(
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
        uri = _put_archive_blob(ctx.settings, job, filtered, "redacted")
    except RuntimeError as exc:
        if "S3_ENDPOINT" in str(exc) or "MASTER_KEY" in str(exc):
            return
        raise
    ctx.uploaded.append(uri)
    try:
        await _set_archived_to(ctx.session, job, uri)
    except Exception:
        _compensate_upload(uri, ctx.settings)
        ctx.uploaded.remove(uri)
        raise


async def _archive_payload(ctx: _RedactCtx, payload: dict[str, Any]) -> None:
    uri = _put_archive_blob(ctx.settings, ctx.job, payload, "full")
    ctx.uploaded.append(uri)
    if not ctx.job.event_id:
        return
    try:
        await _set_archived_to(ctx.session, ctx.job, uri)
    except Exception:
        _compensate_upload(uri, ctx.settings)
        ctx.uploaded.remove(uri)
        raise


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


def _compensate_upload(uri: str, settings: Any) -> None:
    """Best-effort delete of an uploaded archive when DB persist/commit fails."""
    try:
        from app.objectstore_client import delete_uri

        delete_uri(uri, settings=settings)
    except Exception:
        logger.exception("failed to compensate archive upload uri=%s", uri)


def _put_archive_blob(settings: Any, job: _CaptureJob, payload: dict[str, Any], kind: str) -> str:
    from uuid import uuid4

    from app.objectstore_client import put_encrypted_json

    object_id = job.event_id or str(uuid4())
    key = f"{job.org_id}/capture/{kind}/{object_id}.json"
    body = json.dumps(
        {"org_id": job.org_id, "event_id": job.event_id, "payload": payload}
    ).encode()
    return put_encrypted_json(key, body, settings=settings)
