"""Operator platform health surface for Overview (4.P.5 → 4.D.1).

Exposes dependency health, last backup, last restore-drill result, retention
horizon, ingestion lag, DLQ depth, and degraded-mode state — matching the
operator-platform research contract consumed by 4.D.1 Overview.

Auth: provisional dashboard session cookie + OPERATOR_METADATA_READ.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import httpx
from authclient.permissions import OPERATOR_METADATA_READ
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz import assert_operator_permission
from app.db import session_with_org
from app.operator_session_auth import OperatorSessionAuthorization, require_operator_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/operator/platform", tags=["operator-platform"])

_DEFAULT_RETENTION_DAYS = 90
_DEP_TIMEOUT_SEC = 2.0
# Bandit B108: prefer durable operator state dir over world-writable /tmp.
_BACKUP_STAMP = Path(
    os.environ.get("IBEX_LAST_BACKUP_STAMP", "/var/lib/ibex/backup/last-backup.txt")
)
_DRILL_REPORT = Path(
    os.environ.get(
        "RESTORE_DRILL_REPORT",
        "/var/lib/ibex/restore-drill/restore-drill-report.json",
    )
)

# Ingestion lag reads the newest event the platform actually persisted. ClickHouse
# has no RLS (AGENTS.md §4.3), so the org filter below is the isolation boundary
# and `_ingestion_lag_query` refuses to render without an org.
# `maxOrNull` keeps an org with no rows distinguishable from an event at the epoch;
# `dateDiff` in milliseconds keeps sub-second precision without a float date.
_INGESTION_LAG_QUERY = """
SELECT
  count() AS event_count,
  dateDiff('millisecond', maxOrNull(occurred_at), now64(3)) / 1000.0 AS lag_seconds
FROM ibex.usage_facts
WHERE org_id = toUUID('{org_id}')
""".strip()


class PlatformHealthResponse(BaseModel):
    dependency_health: dict[str, str] = Field(description="ok|degraded|unavailable per dependency")
    last_backup_at: datetime | None = None
    last_restore_drill: dict[str, Any] | None = None
    retention_horizon_days: int = _DEFAULT_RETENTION_DAYS
    ingestion_lag_seconds: float | None = Field(
        default=None,
        description=(
            "Seconds since the newest ingested event for this organization; "
            "null when ClickHouse is unavailable or the org has no events"
        ),
    )
    dlq_depth: int | None = None
    degraded_mode: bool = False
    outbox_max_aggregate_seq: int | None = None
    deploy_image_digest: str | None = None
    observed_at: datetime


def _settings(request: Request) -> Any:
    return request.app.state.settings


async def _require_operator_session(request: Request) -> OperatorSessionAuthorization:
    """Fail closed: live session validation + OPERATOR_METADATA_READ."""
    settings = _settings(request)
    claims = await require_operator_session(request)
    assert_operator_permission(settings, claims.permissions, OPERATOR_METADATA_READ)
    return claims


async def _postgres_status(session_factory: Any) -> str:
    if session_factory is None:
        return "unavailable"
    try:
        async with session_factory() as session:  # type: ignore[misc]
            await session.execute(text("SELECT 1"))
        return "ok"
    except (SQLAlchemyError, OSError, RuntimeError):
        return "unavailable"


async def _auth_status(validator: Any) -> str:
    if validator is None:
        return "unavailable"
    ready = getattr(validator, "ready", None)
    if ready is None:
        return "unavailable"
    try:
        ok = await asyncio.wait_for(ready(), timeout=_DEP_TIMEOUT_SEC)
        return "ok" if ok else "unavailable"
    except (OSError, RuntimeError):
        # TimeoutError is an OSError subclass on CPython 3.x (Sonar redundant catch).
        return "unavailable"


async def _redis_status(redis_url: str | None) -> str:
    if not redis_url:
        return "unavailable"
    try:
        from redis.asyncio import Redis
        from redis.exceptions import RedisError
    except ImportError:
        return "unavailable"
    try:
        client = Redis.from_url(
            redis_url,
            socket_connect_timeout=_DEP_TIMEOUT_SEC,
            socket_timeout=_DEP_TIMEOUT_SEC,
        )
        try:
            pong = await asyncio.wait_for(client.ping(), timeout=_DEP_TIMEOUT_SEC)
            return "ok" if pong else "unavailable"
        finally:
            await client.aclose()
    except (OSError, RuntimeError, RedisError):
        return "unavailable"


async def _dep_health(request: Request) -> dict[str, str]:
    state = request.app.state.api
    settings = _settings(request)
    out: dict[str, str] = {
        "api": "ok" if getattr(state, "ready", False) else "unavailable",
        "postgres": await _postgres_status(getattr(state, "session_factory", None)),
        "auth": await _auth_status(getattr(state, "validator", None)),
        "redis": await _redis_status(getattr(settings, "redis_url", None)),
    }
    return out


def _parse_backup_stamp() -> datetime | None:
    try:
        if not _BACKUP_STAMP.exists():
            return None
        raw = _BACKUP_STAMP.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    parts = raw.rsplit(" ", 1)
    candidate = parts[-1] if parts else raw
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None


def _load_drill() -> dict[str, Any] | None:
    try:
        if not _DRILL_REPORT.exists():
            return None
        parsed = json.loads(_DRILL_REPORT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


async def _outbox_watermark(session: AsyncSession | None, org_id: UUID) -> int | None:
    if session is None:
        return None
    try:
        row = await session.execute(
            text(
                "SELECT COALESCE(MAX(aggregate_seq), 0) FROM ibex_core.evidence_outbox "
                "WHERE org_id = CAST(:org_id AS uuid)"
            ),
            {"org_id": str(org_id)},
        )
        return int(row.scalar_one())
    except (SQLAlchemyError, OSError, RuntimeError, TypeError, ValueError):
        logger.debug("outbox watermark unavailable", exc_info=True)
        return None


def _parse_dlq_depth() -> int | None:
    raw = os.environ.get("IBEX_DLQ_DEPTH")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _clickhouse_dsn(settings: Any) -> str | None:
    """ClickHouse HTTP endpoint, from settings first and the shared env second."""
    for candidate in (
        getattr(settings, "clickhouse_http_url", None),
        os.environ.get("CLICKHOUSE_HTTP_URL"),
        os.environ.get("IBEX_CLICKHOUSE_HTTP_URL"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return None


def _ingestion_lag_query(org_id: UUID | None) -> str:
    """Render the org-scoped lag query; refuse to run without a tenant.

    ClickHouse has no RLS, so an unscoped query would read every tenant's events
    (AGENTS.md §4.3). A missing org is a programming error, not an empty result.
    """
    if not isinstance(org_id, UUID):
        raise TypeError("ingestion lag requires an explicit org_id")
    return _INGESTION_LAG_QUERY.replace("{org_id}", str(org_id))


def _clickhouse_endpoint(dsn: str) -> str:
    """ClickHouse HTTP endpoint with exactly one trailing slash on the path.

    The slash belongs to the path, not the whole URL: a DSN may already carry a
    query string (``?database=ibex``), and concatenating onto the raw string
    would append the slash after the parameters.
    """
    parts = urlsplit(dsn)
    return urlunsplit(parts._replace(path=parts.path.rstrip("/") + "/"))


async def _post_lag_query(dsn: str, sql: str) -> tuple[int, str]:
    """POST the rendered SQL to ClickHouse's HTTP interface."""
    try:
        async with httpx.AsyncClient(timeout=_DEP_TIMEOUT_SEC) as client:
            resp = await client.post(
                _clickhouse_endpoint(dsn),
                content=sql + "\nFORMAT JSONEachRow\n",
                headers={"Content-Type": "text/plain"},
            )
    except httpx.HTTPError as exc:
        raise OSError("clickhouse ingestion lag transport failed") from exc
    return resp.status_code, resp.text


def _lag_from_row(row: Any) -> float | None:
    """Convert one JSONEachRow object to seconds, or None when it carries no event."""
    if not isinstance(row, dict):
        return None
    try:
        if int(row.get("event_count") or 0) < 1:
            return None
        raw = row.get("lag_seconds")
        return None if raw is None else max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def _parse_lag_payload(status_code: int, body: str) -> float | None:
    """Parse the aggregate row; an error status or empty result is unknown."""
    if status_code >= 400:
        logger.warning("clickhouse ingestion lag failed status=%s", status_code)
        return None
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            return _lag_from_row(json.loads(stripped))
        except json.JSONDecodeError:
            logger.warning("clickhouse ingestion lag returned a non-JSON row")
            return None
    return None


async def _ingestion_lag_seconds(dsn: str | None, org_id: UUID) -> float | None:
    """Seconds since the newest ingested event for ``org_id``; None if unknown.

    Never raises and never guesses: an unconfigured ClickHouse, a transport
    failure, an error status, or an org with no events all return None so the
    operator sees "unknown" rather than a fabricated freshness number.
    """
    if not dsn:
        return None
    try:
        sql = _ingestion_lag_query(org_id)
        if f"toUUID('{org_id}')" not in sql:
            raise ValueError("ingestion lag query is missing the org filter")
        status, body = await _post_lag_query(dsn, sql)
        return _parse_lag_payload(status, body)
    except (OSError, RuntimeError, TypeError, ValueError):
        logger.debug("ingestion lag unavailable", exc_info=True)
        return None


@router.get("/health")
async def platform_health(
    request: Request,
    claims: Annotated[OperatorSessionAuthorization, Depends(_require_operator_session)],
) -> PlatformHealthResponse:
    """Read-only platform freshness for operator Overview (4.D.1 consumer)."""
    deps = await _dep_health(request)
    drain = getattr(request.app.state.api, "drain", None)
    draining = bool(drain is not None and getattr(drain, "is_draining", lambda: False)())
    degraded = any(v != "ok" for v in deps.values()) or draining

    session_factory = getattr(request.app.state.api, "session_factory", None)
    outbox_seq: int | None = None
    if session_factory is not None:
        try:
            async with session_with_org(session_factory, str(claims.org_id)) as session:
                outbox_seq = await _outbox_watermark(session, claims.org_id)
        except (SQLAlchemyError, OSError, RuntimeError):
            outbox_seq = None

    last_backup, last_drill, ingestion_lag = await asyncio.gather(
        asyncio.to_thread(_parse_backup_stamp),
        asyncio.to_thread(_load_drill),
        _ingestion_lag_seconds(_clickhouse_dsn(_settings(request)), claims.org_id),
    )

    return PlatformHealthResponse(
        dependency_health=deps,
        last_backup_at=last_backup,
        last_restore_drill=last_drill,
        retention_horizon_days=int(
            getattr(_settings(request), "platform_retention_horizon_days", _DEFAULT_RETENTION_DAYS)
        ),
        ingestion_lag_seconds=ingestion_lag,
        dlq_depth=_parse_dlq_depth(),
        degraded_mode=degraded,
        outbox_max_aggregate_seq=outbox_seq,
        deploy_image_digest=os.environ.get("IBEX_DEPLOY_IMAGE_DIGEST") or None,
        observed_at=datetime.now(UTC),
    )
