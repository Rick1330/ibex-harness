"""Receipted multi-store org deletion saga (Postgres, ClickHouse, Redis, object store)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.celery_app import celery_app
from app.config import get_settings
from app.db import create_engine, create_session_factory, session_as_service_org
from app.task_names import TASK_ORG_DELETE_ORGANIZATION
from app.tasks.base import IbexTask

logger = logging.getLogger(__name__)

# Non-erasable allowlist: saga refuses to target these store names (4.P.4 placeholders).
NON_ERASABLE_STORES: frozenset[str] = frozenset()

_STORES = ("postgres", "clickhouse", "redis", "objectstore")
_CH_TABLES = (
    "llm_traces",
    "mcp_tool_calls",
    "evidence_spans",
    "evidence_assembly_metrics",
)
# Literal query strings keyed by allowlisted table (Bandit B608 — no f-string identifiers).
_CH_DELETE_QUERIES: dict[str, str] = {
    "llm_traces": "ALTER TABLE ibex.llm_traces DELETE WHERE org_id = {org_id:UUID}",
    "mcp_tool_calls": "ALTER TABLE ibex.mcp_tool_calls DELETE WHERE org_id = {org_id:UUID}",
    "evidence_spans": "ALTER TABLE ibex.evidence_spans DELETE WHERE org_id = {org_id:UUID}",
    "evidence_assembly_metrics": (
        "ALTER TABLE ibex.evidence_assembly_metrics DELETE WHERE org_id = {org_id:UUID}"
    ),
}
_CH_COUNT_QUERIES: dict[str, str] = {
    "llm_traces": "SELECT count() FROM ibex.llm_traces WHERE org_id = {org_id:UUID}",
    "mcp_tool_calls": "SELECT count() FROM ibex.mcp_tool_calls WHERE org_id = {org_id:UUID}",
    "evidence_spans": "SELECT count() FROM ibex.evidence_spans WHERE org_id = {org_id:UUID}",
    "evidence_assembly_metrics": (
        "SELECT count() FROM ibex.evidence_assembly_metrics WHERE org_id = {org_id:UUID}"
    ),
}
_REDIS_PREFIX_TEMPLATES = (
    "{org_id}:directive:",
    "{org_id}:memory:",
    "{org_id}:hot_memories:",
    "{org_id}:embed:v1:",
    "{org_id}:session:",
    "{org_id}:idempotency:",
    "idempotency:{org_id}:",
    "session:{org_id}:",
    "ratelimit:{org_id}:",
)

# Explicit evidence + policy cleanup before legacy cascade; soft-cancel org last.
_PG_PRE_CASCADE: tuple[str, ...] = (
    "DELETE FROM ibex_core.evidence_outbox WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.evidence_tool_audits WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.evidence_directive_snapshots WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.evidence_score_candidates WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.evidence_assembly_metrics WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.evidence_events WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.evidence_spans WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.evidence_runs WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.session_events WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.org_capture_policies WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.org_model_policies WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.org_model_policy_meta WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.provider_credentials WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.rate_limit_overrides WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.user_totp_secrets WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.operator_action_ledger WHERE org_id = CAST(:org_id AS uuid)",
    # Only cleared holds — never remove an active hold mid-saga (TOCTOU-safe).
    "DELETE FROM ibex_core.legal_holds WHERE org_id = CAST(:org_id AS uuid) AND cleared_at IS NOT NULL",
)

_CASCADE_STATEMENTS: tuple[str, ...] = (
    "DELETE FROM ibex_core.memory_feedback WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.memory_conflict_escalations WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.memory_relationships WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.memory_labels WHERE org_id = CAST(:org_id AS uuid)",
    "UPDATE ibex_core.memories SET session_id = NULL WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.memories WHERE org_id = CAST(:org_id AS uuid)",
    "UPDATE ibex_core.sessions SET directive_version_id = NULL WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.sessions WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.directive_versions WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.directives WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.tokens WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.agents WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.organization_invites WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.users WHERE org_id = CAST(:org_id AS uuid)",
    """
    UPDATE ibex_core.organizations
    SET status = 'cancelled', deleted_at = COALESCE(deleted_at, NOW())
    WHERE id = CAST(:org_id AS uuid)
    """,
)


@dataclass(frozen=True)
class _JobOutcome:
    job_id: str
    org_id: str
    status: str
    error: str | None = None


@dataclass(frozen=True)
class _StageCtx:
    """Shared saga context for store stages (avoids excess kwargs / deep nesting)."""

    job_id: str
    org_id: str
    settings: Any
    session: Any


@celery_app.task(
    bind=True,
    base=IbexTask,
    name=TASK_ORG_DELETE_ORGANIZATION,
    queue="maintenance",
    soft_time_limit=300,
    time_limit=600,
)
def delete_organization(self: IbexTask, job_id: str, org_id: str, **kwargs: Any) -> dict[str, str]:
    """Execute receipted cross-store org deletion saga."""
    del kwargs
    return asyncio.run(_run_delete(job_id=job_id, org_id=org_id))


async def _run_delete(*, job_id: str, org_id: str) -> dict[str, str]:
    settings = get_settings()
    if not settings.database_url:
        raise ValueError("database_url is required for org deletion")
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with session_as_service_org(factory, org_id) as session:
            ctx = _StageCtx(job_id=job_id, org_id=org_id, settings=settings, session=session)
            return await _execute_claimed_job(ctx, factory)
    finally:
        await engine.dispose()


async def _execute_claimed_job(ctx: _StageCtx, factory: Any) -> dict[str, str]:
    claimed = await _claim_job(ctx.session, job_id=ctx.job_id, org_id=ctx.org_id)
    if not claimed:
        return {"status": "skipped", "reason": "job_not_claimable"}
    try:
        blocked = await _finish_if_hold_blocked(ctx)
        if blocked is not None:
            return blocked
        # Soft-deleted orgs still run remaining store stages (no invented receipts).
        archived_uris = await _collect_archived_uris(ctx.session, ctx.org_id)
        await _run_store_stages(ctx, archived_uris=archived_uris)
        return await _finalize_job(ctx)
    except Exception as exc:
        logger.exception("org deletion failed job_id=%s org_id=%s", ctx.job_id, ctx.org_id)
        await ctx.session.rollback()
        async with session_as_service_org(factory, ctx.org_id) as fail_session:
            await _finish_job(
                fail_session,
                _JobOutcome(
                    job_id=ctx.job_id,
                    org_id=ctx.org_id,
                    status="failed",
                    error=str(exc)[:500],
                ),
            )
        raise


async def _finish_if_hold_blocked(ctx: _StageCtx) -> dict[str, str] | None:
    if not await _has_active_legal_hold(ctx.session, ctx.org_id):
        return None
    await _audit_append(
        ctx.session,
        org_id=ctx.org_id,
        action="org_deletion.hold_blocked",
        payload={"job_id": ctx.job_id},
    )
    await _finish_job(
        ctx.session,
        _JobOutcome(
            job_id=ctx.job_id,
            org_id=ctx.org_id,
            status="hold_blocked",
            error="legal_hold_active",
        ),
    )
    return {"status": "hold_blocked", "job_id": ctx.job_id, "org_id": ctx.org_id}


async def _require_no_hold(session, org_id: str) -> None:
    # Serialize with set_hold (same advisory key) so a hold cannot land mid-stage.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(CAST(:org_id AS text)))"),
        {"org_id": org_id},
    )
    if await _has_active_legal_hold(session, org_id):
        raise RuntimeError("legal_hold_active")


async def _run_one_store(
    ctx: _StageCtx,
    store: str,
    runner: Callable[[], Awaitable[None]],
) -> None:
    if await _receipt_verified(ctx.session, ctx.job_id, store):
        return
    await _require_no_hold(ctx.session, ctx.org_id)
    await runner()
    await _upsert_receipt(ctx.session, job_id=ctx.job_id, store=store, status="verified")


async def _run_store_stages(ctx: _StageCtx, *, archived_uris: list[str]) -> None:
    await _run_one_store(
        ctx,
        "postgres",
        lambda: _stage_postgres(ctx.session, org_id=ctx.org_id),
    )
    await _publish_model_policy_invalidate(ctx.settings, ctx.org_id)

    await _run_one_store(
        ctx,
        "clickhouse",
        lambda: _stage_clickhouse(ctx.settings, org_id=ctx.org_id),
    )
    await _run_one_store(
        ctx,
        "redis",
        lambda: _stage_redis(ctx.settings, org_id=ctx.org_id),
    )
    await _run_one_store(
        ctx,
        "objectstore",
        lambda: _stage_objectstore(ctx.settings, org_id=ctx.org_id, uris=archived_uris),
    )


async def _finalize_job(ctx: _StageCtx) -> dict[str, str]:
    digests = await _receipt_digests(ctx.session, ctx.job_id)
    await _audit_append(
        ctx.session,
        org_id=ctx.org_id,
        action="org_deletion.certificate",
        payload={"job_id": ctx.job_id, "receipts": digests},
    )
    if not await _all_receipts_verified(ctx.session, ctx.job_id):
        await _finish_job(
            ctx.session,
            _JobOutcome(
                job_id=ctx.job_id,
                org_id=ctx.org_id,
                status="failed",
                error="incomplete_receipts",
            ),
        )
        return {"status": "failed", "job_id": ctx.job_id, "org_id": ctx.org_id}
    await _finish_job(
        ctx.session,
        _JobOutcome(job_id=ctx.job_id, org_id=ctx.org_id, status="succeeded"),
    )
    return {"status": "succeeded", "job_id": ctx.job_id, "org_id": ctx.org_id}


async def _claim_job(session, *, job_id: str, org_id: str) -> bool:
    """Claim pending or retry failed (non-hold) jobs; never reclaim succeeded/hold_blocked."""
    result = await session.execute(
        text(
            """
            UPDATE ibex_core.org_deletion_jobs
            SET status = 'running', started_at = COALESCE(started_at, NOW()), error = NULL
            WHERE id = CAST(:job_id AS uuid)
              AND org_id = CAST(:org_id AS uuid)
              AND status IN ('pending', 'failed')
            RETURNING id
            """
        ),
        {"job_id": job_id, "org_id": org_id},
    )
    return result.first() is not None


async def _has_active_legal_hold(session, org_id: str) -> bool:
    result = await session.execute(
        text(
            """
            SELECT 1 FROM ibex_core.legal_holds
            WHERE org_id = CAST(:org_id AS uuid) AND cleared_at IS NULL
            LIMIT 1
            """
        ),
        {"org_id": org_id},
    )
    return result.first() is not None


async def _finish_job(session, outcome: _JobOutcome) -> None:
    await session.execute(
        text(
            """
            UPDATE ibex_core.org_deletion_jobs
            SET status = :status,
                error = :error,
                finished_at = NOW()
            WHERE id = CAST(:job_id AS uuid)
              AND org_id = CAST(:org_id AS uuid)
            """
        ),
        {
            "job_id": outcome.job_id,
            "org_id": outcome.org_id,
            "status": outcome.status,
            "error": outcome.error,
        },
    )


async def _collect_archived_uris(session, org_id: str) -> list[str]:
    result = await session.execute(
        text(
            """
            SELECT DISTINCT archived_to
            FROM ibex_core.session_events
            WHERE org_id = CAST(:org_id AS uuid)
              AND archived_to IS NOT NULL
              AND archived_to <> ''
            """
        ),
        {"org_id": org_id},
    )
    return [str(r[0]) for r in result.fetchall()]


async def _stage_postgres(session, *, org_id: str) -> None:
    for stmt in (*_PG_PRE_CASCADE, *_CASCADE_STATEMENTS):
        await session.execute(text(stmt), {"org_id": org_id})


async def _receipt_verified(session, job_id: str, store: str) -> bool:
    if store in NON_ERASABLE_STORES:
        raise ValueError(f"store {store!r} is non-erasable")
    result = await session.execute(
        text(
            """
            SELECT 1 FROM ibex_core.deletion_store_receipts
            WHERE job_id = CAST(:job_id AS uuid)
              AND store = :store
              AND status = 'verified'
            LIMIT 1
            """
        ),
        {"job_id": job_id, "store": store},
    )
    return result.first() is not None


async def _upsert_receipt(
    session, *, job_id: str, store: str, status: str, error: str | None = None
) -> None:
    if store in NON_ERASABLE_STORES:
        raise ValueError(f"store {store!r} is non-erasable")
    idem = f"{job_id}:{store}:org"
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.deletion_store_receipts (
                job_id, store, scope, status, verified_absent_at, idempotency_key, error
            ) VALUES (
                CAST(:job_id AS uuid), :store, 'org', :status,
                CASE WHEN :status = 'verified' THEN NOW() ELSE NULL END,
                :idem, :error
            )
            ON CONFLICT (job_id, store, idempotency_key) DO UPDATE
            SET status = EXCLUDED.status,
                verified_absent_at = EXCLUDED.verified_absent_at,
                error = EXCLUDED.error,
                updated_at = NOW()
            """
        ),
        {
            "job_id": job_id,
            "store": store,
            "status": status,
            "idem": idem,
            "error": error,
        },
    )


async def _all_receipts_verified(session, job_id: str) -> bool:
    for store in _STORES:
        if not await _receipt_verified(session, job_id, store):
            return False
    return True


async def _receipt_digests(session, job_id: str) -> dict[str, str]:
    result = await session.execute(
        text(
            """
            SELECT store, status, COALESCE(verified_absent_at::text, ''), COALESCE(error, '')
            FROM ibex_core.deletion_store_receipts
            WHERE job_id = CAST(:job_id AS uuid)
            ORDER BY store
            """
        ),
        {"job_id": job_id},
    )
    out: dict[str, str] = {}
    for store, status, verified, err in result.fetchall():
        raw = f"{store}|{status}|{verified}|{err}"
        out[str(store)] = hashlib.sha256(raw.encode()).hexdigest()
    return out


async def _audit_append(session, *, org_id: str, action: str, payload: dict[str, Any]) -> None:
    await session.execute(
        text(
            """
            SELECT * FROM ibex_core.privacy_audit_append(
                CAST(:org_id AS uuid),
                NULL,
                :action,
                'org_deletion',
                'allow',
                'organization',
                :org_id,
                ARRAY[]::TEXT[],
                NULL,
                NULL,
                NULL,
                :corr,
                NULL,
                CAST(:payload AS jsonb)
            )
            """
        ),
        {
            "org_id": org_id,
            "action": action,
            "corr": payload.get("job_id"),
            "payload": json.dumps(payload),
        },
    )


async def _publish_model_policy_invalidate(settings: Any, org_id: str) -> None:
    """Best-effort Redis PUBLISH so proxy cache cannot reinstall deleted policies."""
    redis_url = getattr(settings, "redis_url", None)
    if not redis_url:
        return
    try:
        from redis.asyncio import Redis

        client = Redis.from_url(redis_url, decode_responses=True, socket_timeout=1.0)
        try:
            channel = f"model_policy_updates:{org_id}"
            payload = json.dumps({"v": 1, "org_id": org_id, "epoch": int(time.time())})
            await client.publish(channel, payload)
        finally:
            await client.aclose()
    except Exception:
        logger.warning("model_policy_invalidate_failed", extra={"org_id": org_id}, exc_info=True)


def _clickhouse_dsn(settings: Any) -> str:
    dsn = (
        getattr(settings, "clickhouse_dsn", None)
        or os.environ.get("CLICKHOUSE_DSN")
        or os.environ.get("IBEX_WORKER_CLICKHOUSE_DSN")
    )
    if not dsn or not str(dsn).strip():
        raise RuntimeError("CLICKHOUSE_DSN required for org deletion")
    return str(dsn)


def _ch_unknown_table(body: str) -> bool:
    return "UNKNOWN_TABLE" in body or "doesn't exist" in body.lower()


async def _ch_mutate_table(http: Any, url: str, auth: Any, table: str, org_id: str) -> None:
    mut = _CH_DELETE_QUERIES[table]
    resp = http.post(
        url,
        params={"query": mut, "param_org_id": org_id},
        auth=auth,
        timeout=30.0,
    )
    if resp.status_code >= 400:
        body = resp.text
        if _ch_unknown_table(body):
            return
        raise RuntimeError(f"clickhouse mutate {table}: {resp.status_code}")


async def _ch_wait_absent(
    http: Any, url: str, auth: Any, table: str, org_id: str, deadline: float
) -> None:
    q = _CH_COUNT_QUERIES[table]
    while time.monotonic() < deadline:
        resp = http.post(
            url,
            params={"query": q, "param_org_id": org_id},
            auth=auth,
            timeout=10.0,
        )
        if resp.status_code >= 400:
            body = resp.text
            if _ch_unknown_table(body):
                return
            raise RuntimeError(f"clickhouse count {table}: {resp.status_code}")
        count = int(resp.text.strip() or "0")
        if count == 0:
            return
        await asyncio.sleep(0.5)
    raise TimeoutError(f"clickhouse {table} rows remain for org")


async def _stage_clickhouse(settings: Any, *, org_id: str) -> None:
    from app.extraction.clickhouse_traces import _http_endpoint, shared_clickhouse_client

    dsn = _clickhouse_dsn(settings)
    http = shared_clickhouse_client()
    url, auth = _http_endpoint(dsn)
    deadline = time.monotonic() + 120.0
    for table in _CH_TABLES:
        await _ch_mutate_table(http, url, auth, table, org_id)
    for table in _CH_TABLES:
        await _ch_wait_absent(http, url, auth, table, org_id, deadline)


async def _stage_redis(settings: Any, *, org_id: str) -> None:
    redis_url = getattr(settings, "redis_url", None)
    if not redis_url:
        raise RuntimeError("REDIS_URL required for org deletion")
    from redis.asyncio import Redis

    client = Redis.from_url(redis_url, decode_responses=True, socket_timeout=5.0)
    try:
        for tmpl in _REDIS_PREFIX_TEMPLATES:
            prefix = tmpl.format(org_id=org_id)
            await _scan_delete(client, prefix)
    finally:
        await client.aclose()


async def _scan_delete(client: Any, prefix: str) -> None:
    cursor = 0
    pattern = prefix + "*"
    while True:
        cursor, keys = await client.scan(cursor=cursor, match=pattern, count=200)
        if keys:
            await client.delete(*keys)
        if cursor == 0:
            break


def _s3_endpoint(settings: Any) -> str:
    endpoint = os.environ.get("S3_ENDPOINT") or getattr(settings, "s3_endpoint", None)
    if not endpoint or not str(endpoint).strip():
        raise RuntimeError("S3_ENDPOINT required for org deletion")
    return str(endpoint)


async def _stage_objectstore(settings: Any, *, org_id: str, uris: list[str]) -> None:
    _s3_endpoint(settings)
    from app.objectstore_client import delete_org_prefix, delete_uri

    for uri in uris:
        delete_uri(uri, settings=settings)
    delete_org_prefix(org_id, settings=settings)
