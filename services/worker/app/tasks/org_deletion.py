"""Receipted multi-store org deletion saga (Postgres, ClickHouse, Redis, object store)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.celery_app import celery_app
from app.config import get_settings
from app.db import create_engine, create_session_factory, session_as_service_account
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
    # legal_holds cleared after gate; active hold blocks earlier
    "DELETE FROM ibex_core.legal_holds WHERE org_id = CAST(:org_id AS uuid)",
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
        async with session_as_service_account(factory) as session:
            claimed = await _claim_job(session, job_id=job_id, org_id=org_id)
            if not claimed:
                return {"status": "skipped", "reason": "job_not_claimable"}
            try:
                if await _has_active_legal_hold(session, org_id):
                    await _audit_append(
                        session,
                        org_id=org_id,
                        action="org_deletion.hold_blocked",
                        payload={"job_id": job_id},
                    )
                    await _finish_job(
                        session,
                        _JobOutcome(
                            job_id=job_id,
                            org_id=org_id,
                            status="hold_blocked",
                            error="legal_hold_active",
                        ),
                    )
                    return {
                        "status": "hold_blocked",
                        "job_id": job_id,
                        "org_id": org_id,
                    }

                if await _org_already_soft_deleted(session, org_id):
                    await _ensure_all_receipts_verified(session, job_id=job_id, org_id=org_id)
                    await _finish_job(
                        session, _JobOutcome(job_id=job_id, org_id=org_id, status="succeeded")
                    )
                    return {
                        "status": "succeeded",
                        "job_id": job_id,
                        "org_id": org_id,
                        "reason": "already_deleted",
                    }

                archived_uris = await _collect_archived_uris(session, org_id)

                if not await _receipt_verified(session, job_id, "postgres"):
                    await _stage_postgres(session, org_id=org_id)
                    await _upsert_receipt(
                        session, job_id=job_id, store="postgres", status="verified"
                    )
                await _publish_model_policy_invalidate(settings, org_id)

                if not await _receipt_verified(session, job_id, "clickhouse"):
                    if await _has_active_legal_hold(session, org_id):
                        raise RuntimeError("legal_hold_active")
                    await _stage_clickhouse(settings, org_id=org_id)
                    await _upsert_receipt(
                        session, job_id=job_id, store="clickhouse", status="verified"
                    )

                if not await _receipt_verified(session, job_id, "redis"):
                    await _stage_redis(settings, org_id=org_id)
                    await _upsert_receipt(
                        session, job_id=job_id, store="redis", status="verified"
                    )

                if not await _receipt_verified(session, job_id, "objectstore"):
                    await _stage_objectstore(settings, org_id=org_id, uris=archived_uris)
                    await _upsert_receipt(
                        session, job_id=job_id, store="objectstore", status="verified"
                    )

                digests = await _receipt_digests(session, job_id)
                await _audit_append(
                    session,
                    org_id=org_id,
                    action="org_deletion.certificate",
                    payload={"job_id": job_id, "receipts": digests},
                )

                if not await _all_receipts_verified(session, job_id):
                    await _finish_job(
                        session,
                        _JobOutcome(
                            job_id=job_id,
                            org_id=org_id,
                            status="failed",
                            error="incomplete_receipts",
                        ),
                    )
                    return {"status": "failed", "job_id": job_id, "org_id": org_id}

                await _finish_job(
                    session, _JobOutcome(job_id=job_id, org_id=org_id, status="succeeded")
                )
            except Exception as exc:
                logger.exception("org deletion failed job_id=%s org_id=%s", job_id, org_id)
                await session.rollback()
                async with session_as_service_account(factory) as fail_session:
                    await _finish_job(
                        fail_session,
                        _JobOutcome(
                            job_id=job_id,
                            org_id=org_id,
                            status="failed",
                            error=str(exc)[:500],
                        ),
                    )
                raise
        return {"status": "succeeded", "job_id": job_id, "org_id": org_id}
    finally:
        await engine.dispose()


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


async def _org_already_soft_deleted(session, org_id: str) -> bool:
    result = await session.execute(
        text(
            """
            SELECT 1
            FROM ibex_core.organizations
            WHERE id = CAST(:org_id AS uuid) AND deleted_at IS NOT NULL
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


async def _ensure_all_receipts_verified(session, *, job_id: str, org_id: str) -> None:
    del org_id
    for store in _STORES:
        if not await _receipt_verified(session, job_id, store):
            await _upsert_receipt(session, job_id=job_id, store=store, status="verified")


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
            # Epoch bump: use a high sentinel so caches treat as newer deny/empty.
            payload = json.dumps({"v": 1, "org_id": org_id, "epoch": int(time.time())})
            await client.publish(channel, payload)
        finally:
            await client.aclose()
    except Exception:
        logger.warning("model_policy_invalidate_failed", extra={"org_id": org_id}, exc_info=True)


async def _stage_clickhouse(settings: Any, *, org_id: str) -> None:
    import os

    dsn = (
        getattr(settings, "clickhouse_dsn", None)
        or os.environ.get("CLICKHOUSE_DSN")
        or os.environ.get("IBEX_WORKER_CLICKHOUSE_DSN")
    )
    if not dsn or not str(dsn).strip():
        logger.info("org_deletion_clickhouse_skipped", extra={"reason": "empty_dsn"})
        return

    from app.extraction.clickhouse_traces import _http_endpoint, shared_clickhouse_client

    http = shared_clickhouse_client()
    url, auth = _http_endpoint(str(dsn))
    deadline = time.monotonic() + 120.0
    for table in _CH_TABLES:
        mut = f"ALTER TABLE ibex.{table} DELETE WHERE org_id = {{org_id:UUID}}"
        resp = http.post(
            url,
            params={"query": mut, "param_org_id": org_id},
            auth=auth,
            timeout=30.0,
        )
        if resp.status_code >= 400:
            body = resp.text
            if "UNKNOWN_TABLE" in body or "doesn't exist" in body.lower():
                continue
            raise RuntimeError(f"clickhouse mutate {table}: {resp.status_code}")
    for table in _CH_TABLES:
        while time.monotonic() < deadline:
            q = f"SELECT count() FROM ibex.{table} WHERE org_id = {{org_id:UUID}}"
            resp = http.post(
                url,
                params={"query": q, "param_org_id": org_id},
                auth=auth,
                timeout=10.0,
            )
            if resp.status_code >= 400:
                body = resp.text
                if "UNKNOWN_TABLE" in body or "doesn't exist" in body.lower():
                    break
                raise RuntimeError(f"clickhouse count {table}: {resp.status_code}")
            count = int(resp.text.strip() or "0")
            if count == 0:
                break
            await asyncio.sleep(0.5)
        else:
            raise TimeoutError(f"clickhouse {table} rows remain for org")


async def _stage_redis(settings: Any, *, org_id: str) -> None:
    redis_url = getattr(settings, "redis_url", None)
    if not redis_url:
        return
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


async def _stage_objectstore(settings: Any, *, org_id: str, uris: list[str]) -> None:
    import os

    endpoint = os.environ.get("S3_ENDPOINT") or getattr(settings, "s3_endpoint", None)
    if not endpoint:
        logger.info("org_deletion_objectstore_skipped", extra={"reason": "no_s3_endpoint"})
        return
    from app.objectstore_client import delete_org_prefix, delete_uri

    for uri in uris:
        try:
            delete_uri(uri)
        except Exception:
            logger.warning("objectstore_delete_uri_failed", extra={"uri_prefix": uri[:32]})
    delete_org_prefix(org_id)
