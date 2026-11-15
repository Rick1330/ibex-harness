"""Async capture-policy redaction / archive task (never on proxy hot path)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from prometheus_client import Counter
from sqlalchemy import text

from app.celery_app import celery_app
from app.config import get_settings
from app.db import create_engine, create_session_factory, session_as_app_org
from app.tasks.base import IbexTask

logger = logging.getLogger(__name__)

TASK_APPLY_CAPTURE_REDACTION = "ibex.privacy.apply_capture_redaction"
_DEFAULT_MODE = "metadata_only"
_STRIP_KEYS = frozenset({"raw", "content", "prompt"})
_BIGINT_MAX = 2**63 - 1

CAPTURE_ARCHIVE_WITHOUT_MEMORY_ID = Counter(
    "ibex_worker_capture_archive_without_memory_id_total",
    "Archived capture events that carried no memory id, so no artifact ref was recorded",
)

# One object-store ref and one session-event ref per memory id, written in the
# same transaction as the capture write. Each half is conditional: the object
# reference is recorded only after a successful upload, and the session-event
# reference is recorded whenever the event exists even when S3 is unconfigured.
# The memory-id list is bound as JSON text and expanded server-side: asyncpg
# cannot bind a bare array literal without an explicit cast, and this keeps the
# statement static (no SQL built from values).
_ARTIFACT_REF_INSERT_SQL = """
INSERT INTO ibex_core.memory_artifact_refs
    (org_id, memory_id, store, locator, session_id)
SELECT CAST(:org_id AS uuid),
       ref.memory_id,
       ref.store,
       ref.locator,
       CASE
           WHEN ref.event_id IS NULL THEN NULL
           ELSE (
               SELECT e.session_id
                 FROM ibex_core.session_events e
                WHERE e.id = ref.event_id
                  AND e.org_id = CAST(:org_id AS uuid)
           )
       END
  FROM (
        SELECT CAST(elem.value AS uuid) AS memory_id,
               'objectstore' AS store,
               CAST(:uri AS text) AS locator,
               CAST(:event_id AS bigint) AS event_id
          FROM jsonb_array_elements_text(CAST(:memory_ids AS jsonb)) AS elem(value)
         WHERE CAST(:uri AS text) IS NOT NULL
        UNION ALL
        SELECT CAST(elem.value AS uuid),
               'session_event',
               CAST(:event_id_text AS text),
               CAST(:event_id AS bigint)
          FROM jsonb_array_elements_text(CAST(:memory_ids AS jsonb)) AS elem(value)
         WHERE CAST(:event_id AS bigint) IS NOT NULL
       ) AS ref
ON CONFLICT DO NOTHING
"""


@dataclass(frozen=True)
class _CaptureJob:
    """Bundles Celery kwargs so helpers stay under CodeScene arity limits."""

    org_id: str
    event_id: str | None = None
    agent_id: str | None = None
    payload: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class _ArtifactRefs:
    """Where one archived capture lives, and the memories it belongs to.

    ``event_id`` and ``uri`` are independently optional: a redacted capture with
    no S3 write still records its session-event address, and a full capture with
    no event id still records its object address.
    """

    org_id: str
    memory_ids: tuple[str, ...]
    event_id: int | None = None
    uri: str | None = None


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


def _coerce_event_id(event_id: str | int | None) -> int | None:
    """Coerce a Celery JSON string id into the bigint ``session_events.id``.

    Celery serialises task kwargs as JSON, so ``event_id`` arrives as a string
    even though the column is ``bigint``. Binding the raw string makes asyncpg
    raise ``DataError``; coerce once here so a numeric string persists and a
    non-numeric id fails with a clear ``ValueError``.
    """
    if event_id is None:
        return None
    return _require_bigint(_numeric_event_id(event_id), event_id)


def _numeric_event_id(event_id: str | int) -> int:
    """Return the integer value of a non-``None`` id, rejecting non-numeric types."""
    if isinstance(event_id, bool):
        raise TypeError(f"event_id must be an integer, got bool: {event_id!r}")
    if isinstance(event_id, int):
        return event_id
    if isinstance(event_id, str) and event_id.strip().isdigit():
        return int(event_id.strip())
    raise ValueError(f"event_id must be a numeric string: {event_id!r}")


def _require_bigint(value: int, event_id: str | int) -> int:
    """Return ``value`` unchanged when it fits the ``bigint`` column, else fail."""
    if not 0 <= value <= _BIGINT_MAX:
        raise ValueError(f"event_id is outside the bigint range: {event_id!r}")
    return value


async def _run(job: _CaptureJob) -> dict[str, str]:
    """Run one capture job through the tenant-pinned worker login."""
    settings = get_settings()
    if not settings.database_url:
        raise ValueError("database_url is required")
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    uploaded: list[str] = []
    try:
        async with session_as_app_org(factory, job.org_id) as session:
            parsed_agent = UUID(job.agent_id) if job.agent_id else None
            mode = await resolve_capture_mode(session, org_id=job.org_id, agent_id=parsed_agent)
            ctx = _RedactCtx(session=session, settings=settings, job=job, uploaded=uploaded)
            return await _apply_mode(ctx, mode)
    except Exception:
        for uri in uploaded:
            _compensate_upload(uri, job.org_id, settings)
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
                    -- CAST gives the parameter a type when it binds NULL;
                    -- asyncpg rejects a bare `$n IS NULL`.
                    (CAST(:agent_id AS text) IS NULL AND agent_id IS NULL)
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
    """Store the redacted payload and record where its copies live."""
    job = ctx.job
    if not job.event_id:
        return
    event_id = _coerce_event_id(job.event_id)
    memory_ids = await _store_redacted_event(ctx, filtered, event_id)
    uri = _upload_redacted_archive(ctx, filtered)
    if uri is None:
        return
    refs = _ArtifactRefs(
        org_id=job.org_id, memory_ids=memory_ids, event_id=event_id, uri=uri
    )
    await _link_redacted_archive(ctx, refs, uri)


async def _store_redacted_event(
    ctx: _RedactCtx, filtered: dict[str, Any], event_id: int
) -> tuple[str, ...]:
    """Write the redacted payload and the event's own erasure address.

    The session-event link is written with the data update, not with the archive:
    a capture whose S3 write is skipped (missing endpoint or key) must still have
    an erasure address for the event that carries the memory. The memory ids are
    returned so the uploaded object's ref reuses the same set.
    """
    job = ctx.job
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
            "event_id": event_id,
            "org_id": job.org_id,
            "data": json.dumps(filtered),
        },
    )
    memory_ids = tuple(_memory_ids(filtered))
    await _record_artifact_refs(
        ctx.session,
        _ArtifactRefs(org_id=job.org_id, memory_ids=memory_ids, event_id=event_id),
    )
    return memory_ids


def _upload_redacted_archive(ctx: _RedactCtx, filtered: dict[str, Any]) -> str | None:
    """Upload the redacted capture, or None when the object store is unconfigured.

    A missing endpoint or master key is a deployment shape this path tolerates:
    the event is redacted and carries its erasure address either way, so the run
    is not a failure. Any other upload error propagates.
    """
    try:
        uri = _put_archive_blob(ctx.settings, ctx.job, filtered, "redacted")
    except RuntimeError as exc:
        if _object_store_unconfigured(exc):
            return None
        raise
    ctx.uploaded.append(uri)
    return uri


def _object_store_unconfigured(exc: RuntimeError) -> bool:
    """Whether an upload error is the documented missing-configuration shape."""
    return "S3_ENDPOINT" in str(exc) or "MASTER_KEY" in str(exc)


async def _link_redacted_archive(
    ctx: _RedactCtx, refs: _ArtifactRefs, uri: str
) -> None:
    """Point the event at the uploaded copy, undoing the upload if that fails."""
    try:
        if refs.memory_ids:
            await _record_artifact_refs(ctx.session, refs)
        await _set_archived_to(ctx.session, ctx.job, uri)
    except Exception:
        _discard_upload(ctx, uri)
        raise


async def _archive_payload(ctx: _RedactCtx, payload: dict[str, Any]) -> None:
    uri = _put_archive_blob(ctx.settings, ctx.job, payload, "full")
    ctx.uploaded.append(uri)
    event_id = _coerce_event_id(ctx.job.event_id) if ctx.job.event_id else None
    memory_ids = tuple(_memory_ids(payload))
    try:
        # The object reference does not require an event id: a full capture with
        # a usable memory id is still reachable by erasure without one.
        await _record_artifact_refs(
            ctx.session,
            _ArtifactRefs(
                org_id=ctx.job.org_id,
                memory_ids=memory_ids,
                event_id=event_id,
                uri=uri,
            ),
        )
        if event_id is not None:
            await _set_archived_to(ctx.session, ctx.job, uri)
    except Exception:
        _discard_upload(ctx, uri)
        raise


async def _set_archived_to(session, job: _CaptureJob, uri: str) -> None:
    event_id = _coerce_event_id(job.event_id)
    result = await session.execute(
        text(
            """
            UPDATE ibex_core.session_events
            SET archived_to = :uri
            WHERE id = CAST(:event_id AS bigint)
              AND org_id = CAST(:org_id AS uuid)
            """
        ),
        {"event_id": event_id, "org_id": job.org_id, "uri": uri},
    )
    if result.rowcount == 0:
        raise RuntimeError(
            f"session_events archive update matched 0 rows event_id={job.event_id}"
        )


async def _record_artifact_refs(session: Any, refs: _ArtifactRefs) -> None:
    """Record where the archived copy of each memory lives, in this transaction.

    A memory forget can only erase what it can find. The archive URI and the
    capture event are not derivable from the memory row, so the link is written
    here — the one point where the memory ids, the object URI and the event id
    are in hand. Each half is independent: a session-event ref is written with
    the event even when S3 is unconfigured, and an object ref is written after a
    successful upload even when the job carries no event id. A payload with no
    memory id writes no ref, because a fabricated link would send an erasure to
    another tenant's object; the event is counted instead so the coverage hole is
    visible rather than silent.

    ``ON CONFLICT DO NOTHING`` makes a redelivered event a no-op: the unique key
    is ``(org_id, memory_id, store, locator)``.
    """
    if not refs.memory_ids:
        CAPTURE_ARCHIVE_WITHOUT_MEMORY_ID.inc()
        return
    if refs.uri is None and refs.event_id is None:
        return
    await session.execute(text(_ARTIFACT_REF_INSERT_SQL), _artifact_ref_params(refs))


def _artifact_ref_params(refs: _ArtifactRefs) -> dict[str, Any]:
    return {
        "org_id": refs.org_id,
        "event_id": refs.event_id,
        "event_id_text": None if refs.event_id is None else str(refs.event_id),
        "uri": refs.uri,
        "memory_ids": json.dumps(list(refs.memory_ids)),
    }


def _memory_ids(payload: dict[str, Any] | None) -> list[str]:
    """Canonical memory ids the payload links to, deduped, in first-seen order.

    Only the documented capture shapes are read: ``memory_ids`` (a
    ``memory_read`` event) and ``memory_id`` (a single-memory event). An id that
    is not a UUID cannot name a memory and is dropped with a warning that carries
    counts only, never payload content.
    """
    if not payload:
        return []
    found: dict[str, None] = {}
    unusable = 0
    for value in _raw_memory_ids(payload):
        memory_id = _canonical_memory_id(value)
        if memory_id is None:
            unusable += 1
            continue
        found.setdefault(memory_id, None)
    if unusable:
        logger.warning(
            "capture archive payload carried %d unusable memory id value(s); "
            "no ref recorded for them",
            unusable,
        )
    return list(found)


def _raw_memory_ids(payload: dict[str, Any]) -> list[Any]:
    """Every raw memory id value a capture payload carries, unvalidated."""
    values: list[Any] = []
    memory_ids = payload.get("memory_ids")
    if isinstance(memory_ids, list):
        values.extend(memory_ids)
    memory_id = payload.get("memory_id")
    if memory_id is not None:
        values.append(memory_id)
    return values


def _canonical_memory_id(value: Any) -> str | None:
    """The canonical text form of a memory id, or None when it is not a UUID."""
    if isinstance(value, bool) or not isinstance(value, (str, UUID)):
        return None
    try:
        return str(UUID(str(value)))
    except ValueError:
        return None


def _discard_upload(ctx: _RedactCtx, uri: str) -> None:
    """Delete an upload and drop it from the ledger after a failed persist."""
    _compensate_upload(uri, ctx.job.org_id, ctx.settings)
    ctx.uploaded.remove(uri)


def _compensate_upload(uri: str, org_id: str, settings: Any) -> None:
    """Best-effort delete of an uploaded archive when DB persist/commit fails."""
    try:
        from app.objectstore_client import delete_uri

        delete_uri(uri, org_id=org_id, settings=settings)
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
