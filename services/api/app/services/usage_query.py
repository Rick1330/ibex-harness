"""Constrained usage_facts query execution (Python twin of packages/usagequery).

SQL templates are kept in sync with Go RenderSQL via golden fixtures under
packages/usagequery/testdata/. Temporary until a dedicated query service exists.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from apierror_py import SERVICE_DEGRADED, VALIDATION_ERROR
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.errors import ApiError
from app.schemas.billing import UsageQueryRequest, UsageQueryResponse

logger = logging.getLogger(__name__)

_USAGE_QUERY_FAILED = "Usage query failed"
_MAX_RANGE = timedelta(days=31)
_MAX_ROWS = 10_000
_MAX_CONCURRENT = 4
_INFLIGHT_TTL_SECONDS = 120
_REDIS_SOCKET_TIMEOUT_SECONDS = 1.0

# Golden-compatible templates (org_id always first bind).
_SQL_ORG_TIME = """
SELECT
  toStartOfHour(occurred_at) AS bucket,
  sum(input_tokens) AS input_tokens,
  sum(output_tokens) AS output_tokens,
  sum(estimated_cost_cents) AS estimated_cost_cents,
  count() AS requests,
  if(countIf(completeness != 'complete') = 0, 'complete', 'partial') AS completeness
FROM ibex.usage_facts
WHERE org_id = {org_id:UUID}
  AND occurred_at >= {start:DateTime64(3)}
  AND occurred_at < {end:DateTime64(3)}
GROUP BY bucket
ORDER BY bucket
LIMIT {limit:UInt32}
SETTINGS max_rows_to_read = {max_rows:UInt64}
""".strip()

_SQL_AGENT = """
SELECT
  agent_id,
  sum(input_tokens) AS input_tokens,
  sum(output_tokens) AS output_tokens,
  sum(estimated_cost_cents) AS estimated_cost_cents,
  count() AS requests,
  if(countIf(completeness != 'complete') = 0, 'complete', 'partial') AS completeness
FROM ibex.usage_facts
WHERE org_id = {org_id:UUID}
  AND occurred_at >= {start:DateTime64(3)}
  AND occurred_at < {end:DateTime64(3)}
  {agent_pred}
GROUP BY agent_id
ORDER BY estimated_cost_cents DESC
LIMIT {limit:UInt32}
SETTINGS max_rows_to_read = {max_rows:UInt64}
""".strip()

_SQL_REQUEST = """
SELECT
  request_id, org_id, agent_id, provider, model,
  original_model, fallback_model, fallback_reason,
  input_tokens, output_tokens, total_tokens,
  estimated_cost_cents, actual_cost_cents, rate_card_version,
  completeness, occurred_at
FROM ibex.usage_facts
WHERE org_id = {org_id:UUID}
  AND request_id = {request_id:String}
  AND occurred_at >= {start:DateTime64(3)}
  AND occurred_at < {end:DateTime64(3)}
LIMIT 1
SETTINGS max_rows_to_read = {max_rows:UInt64}
""".strip()

_SQL_FALLBACK = """
SELECT
  original_model,
  fallback_model,
  fallback_reason,
  count() AS requests,
  sum(estimated_cost_cents) AS estimated_cost_cents,
  if(countIf(completeness != 'complete') = 0, 'complete', 'partial') AS completeness
FROM ibex.usage_facts
WHERE org_id = {org_id:UUID}
  AND occurred_at >= {start:DateTime64(3)}
  AND occurred_at < {end:DateTime64(3)}
  AND fallback_model IS NOT NULL
GROUP BY original_model, fallback_model, fallback_reason
ORDER BY requests DESC
LIMIT {limit:UInt32}
SETTINGS max_rows_to_read = {max_rows:UInt64}
""".strip()

_SQL_TOOL = """
SELECT
  f.request_id,
  f.agent_id,
  f.model,
  f.estimated_cost_cents,
  f.completeness,
  f.occurred_at,
  t.tool_name,
  t.latency_ms,
  t.success,
  t.error_code
FROM ibex.usage_facts AS f
INNER JOIN ibex.mcp_tool_calls AS t
  ON t.org_id = f.org_id AND t.request_id = f.request_id
WHERE f.org_id = {org_id:UUID}
  AND f.occurred_at >= {start:DateTime64(3)}
  AND f.occurred_at < {end:DateTime64(3)}
ORDER BY f.occurred_at DESC
LIMIT {limit:UInt32}
SETTINGS max_rows_to_read = {max_rows:UInt64}
""".strip()

TEMPLATES: dict[str, str] = {
    "org_time_aggregate": _SQL_ORG_TIME,
    "agent_session_breakdown": _SQL_AGENT,
    "request_point_lookup": _SQL_REQUEST,
    "fallback_attribution": _SQL_FALLBACK,
    "tool_correlation": _SQL_TOOL,
}


def inflight_key(org_id: UUID) -> str:
    return f"org_id:{org_id}:usagequery:inflight"


def _redis_client(redis_url: str) -> Redis:
    return Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=_REDIS_SOCKET_TIMEOUT_SECONDS,
        socket_timeout=_REDIS_SOCKET_TIMEOUT_SECONDS,
    )


def validate_query(org_id: UUID, body: UsageQueryRequest) -> int:
    if org_id is None:
        raise ApiError(code=VALIDATION_ERROR, message="org_id is required")
    if body.end - body.start > _MAX_RANGE:
        raise ApiError(code=VALIDATION_ERROR, message="time range exceeds maximum")
    if body.shape == "request_point_lookup" and not body.request_id:
        raise ApiError(code=VALIDATION_ERROR, message="request_id is required")
    limit = body.limit or _MAX_ROWS
    if limit > _MAX_ROWS:
        raise ApiError(code=VALIDATION_ERROR, message="limit exceeds max_rows")
    return limit


def _derive_completeness(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "partial"
    values = {str(r.get("completeness") or "partial") for r in rows}
    if values == {"complete"}:
        return "complete"
    if "complete" in values:
        return "partial"
    return "partial"


async def execute_usage_query(
    *,
    org_id: UUID,
    body: UsageQueryRequest,
    redis_url: str | None,
    clickhouse_url: str | None,
) -> UsageQueryResponse:
    limit = validate_query(org_id, body)
    await _acquire_inflight(redis_url, org_id)
    try:
        fetched = await _run_clickhouse(org_id, body, limit + 1, clickhouse_url)
    finally:
        await _release_inflight(redis_url, org_id)
    truncated = len(fetched) > limit
    rows = fetched[:limit]
    return UsageQueryResponse(
        shape=body.shape,
        org_id=org_id,
        rows=rows,
        completeness=_derive_completeness(rows),
        truncated=truncated,
    )


_INFLIGHT_LUA = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
if n > tonumber(ARGV[2]) then
  redis.call('DECR', KEYS[1])
  return -1
end
if redis.call('TTL', KEYS[1]) < 0 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return n
"""


async def _acquire_inflight(redis_url: str | None, org_id: UUID) -> None:
    if not redis_url:
        return
    client = _redis_client(redis_url)
    try:
        key = inflight_key(org_id)
        try:
            n = await client.eval(
                _INFLIGHT_LUA, 1, key, str(_INFLIGHT_TTL_SECONDS), str(_MAX_CONCURRENT)
            )
        except RedisError as exc:
            raise ApiError(
                code=SERVICE_DEGRADED,
                message="Usage query concurrency limit unavailable",
            ) from exc
        if int(n) < 0:
            raise ApiError(
                code=SERVICE_DEGRADED,
                message="Too many concurrent usage queries for this organization",
            )
    finally:
        await client.aclose()


async def _release_inflight(redis_url: str | None, org_id: UUID) -> None:
    if not redis_url:
        return
    client = _redis_client(redis_url)
    try:
        await client.decr(inflight_key(org_id))
    except RedisError as exc:
        logger.warning("usagequery inflight release failed: %s", exc)
    finally:
        await client.aclose()


async def _run_clickhouse(
    org_id: UUID,
    body: UsageQueryRequest,
    limit: int,
    clickhouse_url: str | None,
) -> list[dict[str, Any]]:
    dsn = clickhouse_url or os.environ.get("CLICKHOUSE_HTTP_URL") or os.environ.get(
        "IBEX_CLICKHOUSE_HTTP_URL"
    )
    if not dsn:
        logger.info("usage query skipped: clickhouse not configured")
        return []
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover
        raise ApiError(code=SERVICE_DEGRADED, message="ClickHouse client unavailable") from exc

    sql = TEMPLATES[body.shape]
    safe_sql = _bind_literals(sql, org_id, body, limit)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                dsn.rstrip("/") + "/",
                content=safe_sql + "\nFORMAT JSONEachRow\n",
                headers={"Content-Type": "text/plain"},
            )
    except httpx.HTTPError as exc:
        logger.warning("clickhouse usage query transport failed: %s", exc)
        raise ApiError(code=SERVICE_DEGRADED, message=_USAGE_QUERY_FAILED) from exc
    if resp.status_code >= 400:
        logger.warning("clickhouse usage query failed status=%s", resp.status_code)
        raise ApiError(code=SERVICE_DEGRADED, message=_USAGE_QUERY_FAILED)
    rows: list[dict[str, Any]] = []
    for line in resp.text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ApiError(code=SERVICE_DEGRADED, message=_USAGE_QUERY_FAILED) from exc
    return rows


def _fmt_ts(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _bind_literals(sql: str, org_id: UUID, body: UsageQueryRequest, limit: int) -> str:
    """Substitute only typed scalars (UUID / RFC3339 / ints) — never user free text as SQL id."""
    out = sql
    agent_pred = ""
    if body.shape == "agent_session_breakdown" and body.agent_id is not None:
        agent_pred = f"AND agent_id = toUUID('{body.agent_id}')"
    out = out.replace("{agent_pred}", agent_pred)
    out = out.replace("{org_id:UUID}", f"toUUID('{org_id}')")
    out = out.replace("{start:DateTime64(3)}", f"toDateTime64('{_fmt_ts(body.start)}', 3, 'UTC')")
    out = out.replace("{end:DateTime64(3)}", f"toDateTime64('{_fmt_ts(body.end)}', 3, 'UTC')")
    out = out.replace("{limit:UInt32}", str(int(limit)))
    out = out.replace("{max_rows:UInt64}", str(int(_MAX_ROWS)))
    if body.request_id:
        rid = body.request_id.replace("\\", "\\\\").replace("'", "\\'")
        out = out.replace("{request_id:String}", f"'{rid}'")
    return out
