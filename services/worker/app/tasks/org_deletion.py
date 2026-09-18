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
        early, archived_uris = await _claim_and_purge_postgres(
            _ClaimPurgeArgs(factory=factory, job_id=job_id, org_id=org_id, settings=settings)
        )
        if early is not None:
            return early
        # Invalidate only after postgres purge transaction committed.
        return await _run_post_postgres(
            _PostPostgresArgs(
                factory=factory,
                job_id=job_id,
                org_id=org_id,
                settings=settings,
                archived_uris=archived_uris or [],
            )
        )
    finally:
        await engine.dispose()


@dataclass(frozen=True)
class _ClaimPurgeArgs:
    factory: Any
    job_id: str
    org_id: str
    settings: Any


@dataclass(frozen=True)
class _PostPostgresArgs:
    factory: Any
    job_id: str
    org_id: str
    settings: Any
    archived_uris: list[str]


async def _claim_and_purge_postgres(
    args: _ClaimPurgeArgs,
) -> tuple[dict[str, str] | None, list[str] | None]:
    """Claim job + postgres purge in one txn. Returns (early_result, archived_uris)."""
    try:
        async with session_as_service_org(args.factory, args.org_id) as session:
            ctx = _StageCtx(
                job_id=args.job_id,
                org_id=args.org_id,
                settings=args.settings,
                session=session,
            )
            claimed = await _claim_job(session, job_id=args.job_id, org_id=args.org_id)
            if not claimed:
                return {"status": "skipped", "reason": "job_not_claimable"}, None
            blocked = await _finish_if_hold_blocked(ctx)
            if blocked is not None:
                return blocked, None
            # Soft-deleted orgs still run remaining store stages (no invented receipts).
            archived_uris = await _collect_archived_uris(session, args.org_id)
            await _run_one_store(
                ctx,
                "postgres",
                lambda: _stage_postgres(session, org_id=args.org_id),
            )
            return None, archived_uris
    except Exception as exc:
        # Covers body failures and commit-on-exit from session_as_service_org.
        await _record_job_failed(
            args.factory,
            job_id=args.job_id,
            org_id=args.org_id,
            exc=exc,
        )
        raise


async def _run_post_postgres(args: _PostPostgresArgs) -> dict[str, str]:
    """Publish cache invalidation then optional stores + finalize (new txn)."""
    try:
        # Fail closed: invalidation errors must mark the job failed for retry.
        await _publish_model_policy_invalidate(args.settings, args.org_id)
    except Exception as exc:
        await _record_job_failed(
            args.factory,
            job_id=args.job_id,
            org_id=args.org_id,
            exc=exc,
        )
        raise

    try:
        async with session_as_service_org(args.factory, args.org_id) as session:
            ctx = _StageCtx(
                job_id=args.job_id,
                org_id=args.org_id,
                settings=args.settings,
                session=session,
            )
            await _run_optional_store_stages(ctx, archived_uris=args.archived_uris)
            return await _finalize_job(ctx)
    except Exception as exc:
        # Covers body failures and commit-on-exit (inner try would miss commit errors).
        await _record_job_failed(
            args.factory,
            job_id=args.job_id,
            org_id=args.org_id,
            exc=exc,
        )
        raise


async def _record_job_failed(
    factory: Any,
    *,
    job_id: str,
    org_id: str,
    exc: Exception,
) -> None:
    """Mark job failed in a fresh txn (safe after a closed/failed stage session)."""
    logger.exception("org deletion failed job_id=%s org_id=%s", job_id, org_id)
    async with session_as_service_org(factory, org_id) as fail_session:
        await _finish_job(
            fail_session,
            _JobOutcome(
                job_id=job_id,
                org_id=org_id,
                status="failed",
                error=str(exc)[:500],
            ),
        )


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
    await _upsert_receipt(
        ctx.session, _ReceiptWrite(job_id=ctx.job_id, store=store, status="verified")
    )


async def _run_optional_store_stages(ctx: _StageCtx, *, archived_uris: list[str]) -> None:
    await _run_optional_store(
        ctx,
        "clickhouse",
        _clickhouse_configured(ctx.settings),
        lambda: _stage_clickhouse(ctx.settings, org_id=ctx.org_id),
    )
    await _run_optional_store(
        ctx,
        "redis",
        _redis_configured(ctx.settings),
        lambda: _stage_redis(ctx.settings, org_id=ctx.org_id),
    )
    await _run_optional_store(
        ctx,
        "objectstore",
        _objectstore_configured(ctx.settings),
        lambda: _stage_objectstore(ctx.settings, org_id=ctx.org_id, uris=archived_uris),
    )


async def _run_optional_store(
    ctx: _StageCtx,
    store: str,
    configured: bool,
    runner: Callable[[], Awaitable[None]],
) -> None:
    if await _receipt_verified(ctx.session, ctx.job_id, store):
        return
    if not configured:
        # Deployment has no such store: nothing to purge; record verified absence.
        await _upsert_receipt(
            ctx.session,
            _ReceiptWrite(
                job_id=ctx.job_id,
                store=store,
                status="verified",
                error="unconfigured",
            ),
        )
        return
    await _require_no_hold(ctx.session, ctx.org_id)
    await runner()
    await _upsert_receipt(
        ctx.session, _ReceiptWrite(job_id=ctx.job_id, store=store, status="verified")
    )


async def _finalize_job(ctx: _StageCtx) -> dict[str, str]:
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
    digests = await _receipt_digests(ctx.session, ctx.job_id)
    await _audit_append(
        ctx.session,
        org_id=ctx.org_id,
        action="org_deletion.certificate",
        payload={"job_id": ctx.job_id, "receipts": digests},
    )
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


@dataclass(frozen=True, slots=True)
class _ReceiptWrite:
    job_id: str
    store: str
    status: str
    error: str | None = None


async def _upsert_receipt(session, receipt: _ReceiptWrite) -> None:
    await _upsert_receipt_write(session, receipt)


async def _upsert_receipt_write(session, receipt: _ReceiptWrite) -> None:
    if receipt.store in NON_ERASABLE_STORES:
        raise ValueError(f"store {receipt.store!r} is non-erasable")
    idem = f"{receipt.job_id}:{receipt.store}:org"
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
            "job_id": receipt.job_id,
            "store": receipt.store,
            "status": receipt.status,
            "idem": idem,
            "error": receipt.error,
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
    """Redis PUBLISH so proxy cache cannot reinstall deleted policies. Failures propagate."""
    redis_url = getattr(settings, "redis_url", None)
    if not redis_url:
        return
    from redis.asyncio import Redis

    client = Redis.from_url(redis_url, decode_responses=True, socket_timeout=1.0)
    try:
        channel = f"model_policy_updates:{org_id}"
        payload = json.dumps({"v": 1, "org_id": org_id, "epoch": int(time.time())})
        await client.publish(channel, payload)
    finally:
        await client.aclose()


def _clickhouse_configured(settings: Any) -> bool:
    dsn = (
        getattr(settings, "clickhouse_dsn", None)
        or os.environ.get("CLICKHOUSE_DSN")
        or os.environ.get("IBEX_WORKER_CLICKHOUSE_DSN")
    )
    return bool(dsn and str(dsn).strip())


def _redis_configured(settings: Any) -> bool:
    return bool(getattr(settings, "redis_url", None))


def _objectstore_configured(settings: Any) -> bool:
    endpoint = os.environ.get("S3_ENDPOINT") or getattr(settings, "s3_endpoint", None)
    return bool(endpoint and str(endpoint).strip())


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


@dataclass(frozen=True, slots=True)
class _CHClient:
    http: Any
    url: str
    auth: Any


@dataclass(frozen=True, slots=True)
class _CHOp:
    client: _CHClient
    table: str
    org_id: str


def _ch_mutate_table(op: _CHOp) -> None:
    mut = _CH_DELETE_QUERIES[op.table]
    resp = op.client.http.post(
        op.client.url,
        params={"query": mut, "param_org_id": op.org_id},
        auth=op.client.auth,
        timeout=30.0,
    )
    if resp.status_code >= 400:
        body = resp.text
        if _ch_unknown_table(body):
            return
        raise RuntimeError(f"clickhouse mutate {op.table}: {resp.status_code}")


async def _ch_wait_absent(op: _CHOp, deadline: float) -> None:
    q = _CH_COUNT_QUERIES[op.table]
    while time.monotonic() < deadline:
        count = await _ch_count_org(op, q)
        if count == 0:
            return
        await asyncio.sleep(0.5)
    raise TimeoutError(f"clickhouse {op.table} rows remain for org")


async def _ch_count_org(op: _CHOp, query: str) -> int:
    resp = await asyncio.to_thread(
        op.client.http.post,
        op.client.url,
        params={"query": query, "param_org_id": op.org_id},
        auth=op.client.auth,
        timeout=10.0,
    )
    if resp.status_code < 400:
        return int(resp.text.strip() or "0")
    if _ch_unknown_table(resp.text):
        return 0
    raise RuntimeError(f"clickhouse count {op.table}: {resp.status_code}")


async def _stage_clickhouse(settings: Any, *, org_id: str) -> None:
    from app.extraction.clickhouse_traces import _http_endpoint, shared_clickhouse_client

    dsn = _clickhouse_dsn(settings)
    http = shared_clickhouse_client()
    url, auth = _http_endpoint(dsn)
    client = _CHClient(http=http, url=url, auth=auth)
    deadline = time.monotonic() + 120.0
    for table in _CH_TABLES:
        await asyncio.to_thread(_ch_mutate_table, _CHOp(client, table, org_id))
    for table in _CH_TABLES:
        await _ch_wait_absent(_CHOp(client, table, org_id), deadline)


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


def _delete_objectstore_sync(settings: Any, org_id: str, uris: list[str]) -> None:
    _s3_endpoint(settings)
    from app.objectstore_client import delete_org_prefix, delete_uri

    for uri in uris:
        delete_uri(uri, settings=settings)
    delete_org_prefix(org_id, settings=settings)


async def _stage_objectstore(settings: Any, *, org_id: str, uris: list[str]) -> None:
    await asyncio.to_thread(_delete_objectstore_sync, settings, org_id, uris)
