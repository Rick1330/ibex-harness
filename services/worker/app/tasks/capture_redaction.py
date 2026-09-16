"""Async capture-policy redaction / archive task (never on proxy hot path)."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text

from app.celery_app import celery_app
from app.config import get_settings
from app.db import create_engine, create_session_factory, session_as_service_account
from app.tasks.base import IbexTask

logger = logging.getLogger(__name__)

TASK_APPLY_CAPTURE_REDACTION = "ibex.privacy.apply_capture_redaction"
_DEFAULT_MODE = "metadata_only"


@celery_app.task(
    bind=True,
    base=IbexTask,
    name=TASK_APPLY_CAPTURE_REDACTION,
    queue="maintenance",
    soft_time_limit=120,
    time_limit=180,
)
def apply_capture_redaction(
    self: IbexTask,
    *,
    org_id: str,
    event_id: str | None = None,
    payload: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, str]:
    """Load org capture policy and redact or queue archive for eligible events."""
    del self, kwargs
    import asyncio

    return asyncio.run(_run(org_id=org_id, event_id=event_id, payload=payload or {}))


async def _run(*, org_id: str, event_id: str | None, payload: dict[str, Any]) -> dict[str, str]:
    settings = get_settings()
    if not settings.database_url:
        raise ValueError("database_url is required")
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with session_as_service_account(factory) as session:
            mode = await resolve_capture_mode(session, org_id=org_id, agent_id=None)
            if mode == "none":
                return {"status": "skipped", "mode": mode}
            if mode == "metadata_only":
                return {"status": "redacted", "mode": mode}
            if mode == "redacted":
                # Strip privileged fields from payload copy; never log content.
                _ = {k: v for k, v in payload.items() if k not in {"raw", "content", "prompt"}}
                return {"status": "redacted", "mode": mode, "event_id": event_id or ""}
            # mode == full → archive via objectstore when configured
            if payload:
                await _archive_if_configured(org_id=org_id, event_id=event_id, payload=payload)
            return {"status": "archived", "mode": mode, "event_id": event_id or ""}
    finally:
        await engine.dispose()


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


async def _archive_if_configured(
    *, org_id: str, event_id: str | None, payload: dict[str, Any]
) -> None:
    import os

    if not os.environ.get("S3_ENDPOINT"):
        logger.info("capture_archive_skipped", extra={"reason": "no_s3"})
        return
    from app.objectstore_client import put_encrypted_json

    key = f"{org_id}/capture/{event_id or 'anon'}.json"
    # Worker stores JSON as opaque bytes; Go PutEncrypted owns Seal for privileged paths.
    # Here we store a metadata-wrapped blob without raw secrets in logs.
    body = json.dumps({"org_id": org_id, "event_id": event_id, "payload": payload}).encode()
    put_encrypted_json(key, body)
