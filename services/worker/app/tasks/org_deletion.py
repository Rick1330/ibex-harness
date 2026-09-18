"""Receipted multi-store org deletion saga (Postgres, ClickHouse, Redis, object store)."""

from __future__ import annotations

import asyncio
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
from app.tasks import org_deletion_receipts as _rcpt
from app.tasks import org_deletion_stores as _stores
from app.tasks.base import IbexTask

logger = logging.getLogger(__name__)

# Non-erasable allowlist: saga refuses to target these store names (4.P.4 placeholders).
# Tests monkeypatch this name; receipt helpers read it lazily.
NON_ERASABLE_STORES: frozenset[str] = frozenset()
_STORES = _rcpt.STORES
_ReceiptWrite = _rcpt.ReceiptWrite
_upsert_receipt = _rcpt.upsert_receipt
_receipt_verified = _rcpt.receipt_verified
_receipt_terminal = _rcpt.receipt_terminal
_receipt_status = _rcpt.receipt_status
_parse_deployed_stores = _rcpt.parse_deployed_stores
_store_is_deployed = _rcpt.store_is_deployed
_receipt_digests = _rcpt.receipt_digests
_clickhouse_configured = _stores.clickhouse_configured
_redis_configured = _stores.redis_configured
_objectstore_configured = _stores.objectstore_configured
_stage_clickhouse = _stores.stage_clickhouse
_stage_redis = _stores.stage_redis
_stage_objectstore = _stores.stage_objectstore
_CH_TABLES = _stores.CH_TABLES
_CH_DELETE_QUERIES = _stores.CH_DELETE_QUERIES
_CH_COUNT_QUERIES = _stores.CH_COUNT_QUERIES
_REDIS_PREFIX_TEMPLATES = _stores.REDIS_PREFIX_TEMPLATES


async def _all_receipts_verified(session, job_id: str) -> bool:
    """True only when every store has status=verified (strict; excludes not_applicable)."""
    for store in _STORES:
        if not await _receipt_verified(session, job_id, store):
            return False
    return True


async def _all_receipts_satisfied(session, job_id: str, settings: Any) -> bool:
    """Finalize gate: deployed stores must be verified; others must be not_applicable.

    not_applicable is never treated as verified — digests and this check keep them distinct.
    """
    deployed = _parse_deployed_stores(settings)
    for store in _STORES:
        status = await _receipt_status(session, job_id, store)
        if store in deployed:
            if status != "verified":
                return False
        elif status != "not_applicable":
            return False
    return True


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
            # Persist URIs before purge so object-store retries still see non-prefix archives.
            archived_uris = await _resolve_archived_uris(
                session, job_id=args.job_id, org_id=args.org_id
            )
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
    if await _receipt_terminal(ctx.session, ctx.job_id, store):
        return
    deployed = _store_is_deployed(ctx.settings, store)
    if not deployed:
        # Explicit topology omission — distinct from verified deletion.
        await _upsert_receipt(
            ctx.session,
            _ReceiptWrite(
                job_id=ctx.job_id,
                store=store,
                status="not_applicable",
                error="store_not_deployed",
            ),
        )
        return
    if not configured:
        # Deployed but unreachable/misconfigured — fail closed (never verified-skip).
        await _upsert_receipt(
            ctx.session,
            _ReceiptWrite(
                job_id=ctx.job_id,
                store=store,
                status="failed",
                error="store_unreachable",
            ),
        )
        raise RuntimeError(f"{store} is deployed but unreachable (missing runtime config)")
    await _require_no_hold(ctx.session, ctx.org_id)
    await runner()
    await _upsert_receipt(
        ctx.session, _ReceiptWrite(job_id=ctx.job_id, store=store, status="verified")
    )


async def _finalize_job(ctx: _StageCtx) -> dict[str, str]:
    if not await _all_receipts_satisfied(ctx.session, ctx.job_id, ctx.settings):
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


async def _load_archived_uri_snapshot(session, job_id: str) -> list[str] | None:
    """Return persisted URI list, or None when no snapshot has been written yet."""
    result = await session.execute(
        text(
            """
            SELECT archived_uri_snapshot
            FROM ibex_core.org_deletion_jobs
            WHERE id = CAST(:job_id AS uuid)
            """
        ),
        {"job_id": job_id},
    )
    row = result.first()
    if row is None or row[0] is None:
        return None
    raw = row[0]
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, list):
        return []
    return [str(u) for u in raw]


async def _save_archived_uri_snapshot(session, job_id: str, uris: list[str]) -> None:
    await session.execute(
        text(
            """
            UPDATE ibex_core.org_deletion_jobs
            SET archived_uri_snapshot = CAST(:uris AS jsonb)
            WHERE id = CAST(:job_id AS uuid)
            """
        ),
        {"job_id": job_id, "uris": json.dumps(uris)},
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


async def _resolve_archived_uris(session, *, job_id: str, org_id: str) -> list[str]:
    """Reuse a prior snapshot on retry; otherwise collect + persist before Postgres purge."""
    existing = await _load_archived_uri_snapshot(session, job_id)
    if existing is not None:
        return existing
    uris = await _collect_archived_uris(session, org_id)
    await _save_archived_uri_snapshot(session, job_id, uris)
    return uris


async def _stage_postgres(session, *, org_id: str) -> None:
    for stmt in (*_PG_PRE_CASCADE, *_CASCADE_STATEMENTS):
        await session.execute(text(stmt), {"org_id": org_id})


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
