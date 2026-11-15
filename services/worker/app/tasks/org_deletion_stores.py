"""Optional-store deletion stages (ClickHouse / Redis / objectstore)."""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any

# Literal query strings keyed by allowlisted table (Bandit B608 — no f-string identifiers).
CH_TABLES = (
    "llm_traces",
    "mcp_tool_calls",
    "evidence_spans",
    "evidence_assembly_metrics",
    "usage_facts",
    "evidence_events",
)
CH_DELETE_QUERIES: dict[str, str] = {
    "llm_traces": "ALTER TABLE ibex.llm_traces DELETE WHERE org_id = {org_id:UUID}",
    "mcp_tool_calls": "ALTER TABLE ibex.mcp_tool_calls DELETE WHERE org_id = {org_id:UUID}",
    "evidence_spans": "ALTER TABLE ibex.evidence_spans DELETE WHERE org_id = {org_id:UUID}",
    "evidence_assembly_metrics": (
        "ALTER TABLE ibex.evidence_assembly_metrics DELETE WHERE org_id = {org_id:UUID}"
    ),
    "usage_facts": "ALTER TABLE ibex.usage_facts DELETE WHERE org_id = {org_id:UUID}",
    "evidence_events": "ALTER TABLE ibex.evidence_events DELETE WHERE org_id = {org_id:UUID}",
}
CH_COUNT_QUERIES: dict[str, str] = {
    "llm_traces": "SELECT count() FROM ibex.llm_traces WHERE org_id = {org_id:UUID}",
    "mcp_tool_calls": "SELECT count() FROM ibex.mcp_tool_calls WHERE org_id = {org_id:UUID}",
    "evidence_spans": "SELECT count() FROM ibex.evidence_spans WHERE org_id = {org_id:UUID}",
    "evidence_assembly_metrics": (
        "SELECT count() FROM ibex.evidence_assembly_metrics WHERE org_id = {org_id:UUID}"
    ),
    "usage_facts": "SELECT count() FROM ibex.usage_facts WHERE org_id = {org_id:UUID}",
    "evidence_events": "SELECT count() FROM ibex.evidence_events WHERE org_id = {org_id:UUID}",
}
REDIS_PREFIX_TEMPLATES = (
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

_MUTATE_TIMEOUT_SECONDS = 30.0
_COUNT_TIMEOUT_SECONDS = 10.0

# Single-evidence-event erasure, for the memory forget consumer. ClickHouse has
# no RLS, so the org predicate is what keeps a recorded locator from reaching
# another tenant's row; the event id narrows the mutation to exactly the row the
# artifact ref names instead of every event about a resource.
CH_EVENT_TABLE = "evidence_events"
CH_EVENT_DELETE_QUERY = (
    "ALTER TABLE ibex.evidence_events DELETE"
    " WHERE org_id = {org_id:UUID} AND event_id = {event_id:UUID}"
)
CH_EVENT_COUNT_QUERY = (
    "SELECT count() FROM ibex.evidence_events"
    " WHERE org_id = {org_id:UUID} AND event_id = {event_id:UUID}"
)


def clickhouse_configured(settings: Any) -> bool:
    return _clickhouse_dsn_setting(settings) is not None


def _clickhouse_dsn_setting(settings: Any) -> str | None:
    """The configured ClickHouse DSN as text, or None when it is unset or blank."""
    dsn = (
        getattr(settings, "clickhouse_dsn", None)
        or os.environ.get("CLICKHOUSE_DSN")
        or os.environ.get("IBEX_WORKER_CLICKHOUSE_DSN")
    )
    if dsn is None:
        return None
    text = str(dsn)
    return text if text.strip() else None


def redis_configured(settings: Any) -> bool:
    return bool(getattr(settings, "redis_url", None))


def objectstore_configured(settings: Any) -> bool:
    return _s3_endpoint_setting(settings) is not None


def _s3_endpoint_setting(settings: Any) -> str | None:
    """The configured S3 endpoint as text, or None when it is unset or blank."""
    endpoint = os.environ.get("S3_ENDPOINT") or getattr(settings, "s3_endpoint", None)
    if endpoint is None:
        return None
    text = str(endpoint)
    return text if text.strip() else None


def clickhouse_dsn(settings: Any) -> str:
    dsn = _clickhouse_dsn_setting(settings)
    if dsn is None:
        raise RuntimeError("CLICKHOUSE_DSN required for org deletion")
    return dsn


def _ch_unknown_table(body: str) -> bool:
    return "UNKNOWN_TABLE" in body or "doesn't exist" in body.lower()


@dataclass(frozen=True, slots=True)
class CHClient:
    http: Any
    url: str
    auth: Any


@dataclass(frozen=True, slots=True)
class CHOp:
    """One ClickHouse mutation or count: an org, and optionally one event in it."""

    client: CHClient
    table: str
    org_id: str
    event_id: str | None = None


def _ch_statement(
    op: CHOp, org_queries: dict[str, str], event_query: str
) -> tuple[str, dict[str, str]]:
    """Return the statement and bound params for ``op``.

    Both branches bind the org; only the event branch binds an event id. The
    query text is a literal in every case (Bandit B608 — no built SQL).
    """
    params = {"param_org_id": op.org_id}
    if op.event_id is None:
        return org_queries[op.table], params
    if op.table != CH_EVENT_TABLE:
        # The event queries name ibex.evidence_events literally; pairing them
        # with another table would delete rows the caller did not ask for.
        raise ValueError("event-scoped ClickHouse op requires the evidence table")
    params["param_event_id"] = op.event_id
    return event_query, params


def ch_mutate_table(op: CHOp) -> None:
    """Apply one mutation. A table that does not exist yet has nothing to delete."""
    mut, params = _ch_statement(op, CH_DELETE_QUERIES, CH_EVENT_DELETE_QUERY)
    # A mutation reports no count; only the failure classification matters here.
    _ = _ch_row_count(op, _ch_post(op, mut, params, _MUTATE_TIMEOUT_SECONDS), "mutate")


async def ch_wait_absent(op: CHOp, deadline: float) -> None:
    while time.monotonic() < deadline:
        count = await ch_count(op)
        if count == 0:
            return
        await asyncio.sleep(0.5)
    raise TimeoutError(f"clickhouse {op.table} rows remain for the erased scope")


def _ch_post(op: CHOp, statement: str, params: dict[str, str], timeout: float) -> Any:
    """POST one statement to ClickHouse. The query text is always a literal."""
    return op.client.http.post(
        op.client.url,
        params={"query": statement, **params},
        auth=op.client.auth,
        timeout=timeout,
    )


def _ch_row_count(op: CHOp, resp: Any, verb: str) -> int | None:
    """Rows the response reports, or None when ClickHouse has no such table."""
    if resp.status_code < 400:
        return int(resp.text.strip() or "0")
    if _ch_unknown_table(resp.text):
        return None
    raise RuntimeError(f"clickhouse {verb} {op.table}: {resp.status_code}")


async def ch_count(op: CHOp) -> int:
    query, params = _ch_statement(op, CH_COUNT_QUERIES, CH_EVENT_COUNT_QUERY)
    resp = await asyncio.to_thread(_ch_post, op, query, params, _COUNT_TIMEOUT_SECONDS)
    return _ch_row_count(op, resp, "count") or 0


def clickhouse_client(settings: Any) -> CHClient:
    """Build the HTTP client both ClickHouse paths share (no per-call client)."""
    from app.extraction.clickhouse_traces import _http_endpoint, shared_clickhouse_client

    dsn = clickhouse_dsn(settings)
    url, auth = _http_endpoint(dsn)
    return CHClient(http=shared_clickhouse_client(), url=url, auth=auth)


async def stage_clickhouse(settings: Any, *, org_id: str) -> None:
    client = clickhouse_client(settings)
    deadline = time.monotonic() + 120.0
    for table in CH_TABLES:
        await asyncio.to_thread(ch_mutate_table, CHOp(client, table, org_id))
    for table in CH_TABLES:
        await ch_wait_absent(CHOp(client, table, org_id), deadline)


async def delete_clickhouse_event(
    settings: Any, *, org_id: str, event_id: str, deadline: float
) -> None:
    """Delete one evidence event for one org and wait until it is gone.

    Reused by the memory forget consumer: the same mutate/count machinery as the
    org-wide stage, narrowed to the locator the artifact ref recorded.
    """
    op = CHOp(clickhouse_client(settings), CH_EVENT_TABLE, org_id, event_id=event_id)
    await asyncio.to_thread(ch_mutate_table, op)
    await ch_wait_absent(op, deadline)


async def stage_redis(settings: Any, *, org_id: str) -> None:
    redis_url = getattr(settings, "redis_url", None)
    if not redis_url:
        raise RuntimeError("REDIS_URL required for org deletion")
    from redis.asyncio import Redis

    client = Redis.from_url(redis_url, decode_responses=True, socket_timeout=5.0)
    try:
        for tmpl in REDIS_PREFIX_TEMPLATES:
            prefix = tmpl.format(org_id=org_id)
            await scan_delete(client, prefix)
    finally:
        await client.aclose()


async def scan_delete(client: Any, prefix: str) -> None:
    cursor = 0
    pattern = prefix + "*"
    while True:
        cursor, keys = await client.scan(cursor=cursor, match=pattern, count=200)
        if keys:
            await client.delete(*keys)
        if cursor == 0:
            break


def s3_endpoint(settings: Any) -> str:
    endpoint = os.environ.get("S3_ENDPOINT") or getattr(settings, "s3_endpoint", None)
    if not endpoint or not str(endpoint).strip():
        raise RuntimeError("S3_ENDPOINT required for org deletion")
    return str(endpoint)


def delete_objectstore_sync(settings: Any, org_id: str, uris: list[str]) -> None:
    s3_endpoint(settings)
    from app.objectstore_client import delete_org_prefix, delete_uri

    for uri in uris:
        delete_uri(uri, org_id=org_id, settings=settings)
    delete_org_prefix(org_id, settings=settings)


async def stage_objectstore(settings: Any, *, org_id: str, uris: list[str]) -> None:
    await asyncio.to_thread(delete_objectstore_sync, settings, org_id, uris)
