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
)
CH_DELETE_QUERIES: dict[str, str] = {
    "llm_traces": "ALTER TABLE ibex.llm_traces DELETE WHERE org_id = {org_id:UUID}",
    "mcp_tool_calls": "ALTER TABLE ibex.mcp_tool_calls DELETE WHERE org_id = {org_id:UUID}",
    "evidence_spans": "ALTER TABLE ibex.evidence_spans DELETE WHERE org_id = {org_id:UUID}",
    "evidence_assembly_metrics": (
        "ALTER TABLE ibex.evidence_assembly_metrics DELETE WHERE org_id = {org_id:UUID}"
    ),
}
CH_COUNT_QUERIES: dict[str, str] = {
    "llm_traces": "SELECT count() FROM ibex.llm_traces WHERE org_id = {org_id:UUID}",
    "mcp_tool_calls": "SELECT count() FROM ibex.mcp_tool_calls WHERE org_id = {org_id:UUID}",
    "evidence_spans": "SELECT count() FROM ibex.evidence_spans WHERE org_id = {org_id:UUID}",
    "evidence_assembly_metrics": (
        "SELECT count() FROM ibex.evidence_assembly_metrics WHERE org_id = {org_id:UUID}"
    ),
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


def clickhouse_configured(settings: Any) -> bool:
    dsn = (
        getattr(settings, "clickhouse_dsn", None)
        or os.environ.get("CLICKHOUSE_DSN")
        or os.environ.get("IBEX_WORKER_CLICKHOUSE_DSN")
    )
    return bool(dsn and str(dsn).strip())


def redis_configured(settings: Any) -> bool:
    return bool(getattr(settings, "redis_url", None))


def objectstore_configured(settings: Any) -> bool:
    endpoint = os.environ.get("S3_ENDPOINT") or getattr(settings, "s3_endpoint", None)
    return bool(endpoint and str(endpoint).strip())


def clickhouse_dsn(settings: Any) -> str:
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
class CHClient:
    http: Any
    url: str
    auth: Any


@dataclass(frozen=True, slots=True)
class CHOp:
    client: CHClient
    table: str
    org_id: str


def ch_mutate_table(op: CHOp) -> None:
    mut = CH_DELETE_QUERIES[op.table]
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


async def ch_wait_absent(op: CHOp, deadline: float) -> None:
    q = CH_COUNT_QUERIES[op.table]
    while time.monotonic() < deadline:
        count = await ch_count_org(op, q)
        if count == 0:
            return
        await asyncio.sleep(0.5)
    raise TimeoutError(f"clickhouse {op.table} rows remain for org")


async def ch_count_org(op: CHOp, query: str) -> int:
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


async def stage_clickhouse(settings: Any, *, org_id: str) -> None:
    from app.extraction.clickhouse_traces import _http_endpoint, shared_clickhouse_client

    dsn = clickhouse_dsn(settings)
    http = shared_clickhouse_client()
    url, auth = _http_endpoint(dsn)
    client = CHClient(http=http, url=url, auth=auth)
    deadline = time.monotonic() + 120.0
    for table in CH_TABLES:
        await asyncio.to_thread(ch_mutate_table, CHOp(client, table, org_id))
    for table in CH_TABLES:
        await ch_wait_absent(CHOp(client, table, org_id), deadline)


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
        delete_uri(uri, settings=settings)
    delete_org_prefix(org_id, settings=settings)


async def stage_objectstore(settings: Any, *, org_id: str, uris: list[str]) -> None:
    await asyncio.to_thread(delete_objectstore_sync, settings, org_id, uris)
