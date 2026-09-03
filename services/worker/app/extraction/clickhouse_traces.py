"""Insert extraction usage into ibex.llm_traces (same columns as Go TraceRecord)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import httpx
from prometheus_client import Counter

logger = logging.getLogger(__name__)

CLICKHOUSE_SKIP_COUNTER = Counter(
    "ibex_worker_extraction_clickhouse_skip_total",
    "llm_traces inserts skipped (empty DSN or HTTP failure)",
    ["reason"],
)

_INSERT_SQL = (
    "INSERT INTO ibex.llm_traces ("
    "request_id, org_id, agent_id, session_id, checkpoint_id, "
    "model, provider, is_streaming, "
    "input_tokens, output_tokens, total_tokens, "
    "auth_latency_ms, directive_latency_ms, provider_ttfb_ms, total_latency_ms, "
    "status_code, is_complete, error_code, "
    "requested_at, completed_at"
    ") FORMAT JSONEachRow"
)


class MissingOrgIdError(ValueError):
    """ClickHouse llm_traces insert refused without org_id."""


@dataclass(frozen=True, slots=True)
class ExtractionTraceRow:
    request_id: str
    org_id: UUID | None
    agent_id: UUID
    session_id: UUID | None
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    provider_ttfb_ms: int
    total_latency_ms: int
    status_code: int
    is_complete: bool
    error_code: str
    requested_at: datetime
    completed_at: datetime


def insert_extraction_trace(
    *,
    dsn: str | None,
    row: ExtractionTraceRow,
    client: httpx.Client | None = None,
) -> bool:
    """Insert one llm_traces row. Empty DSN fail-opens. Never stores prompt text."""
    if row.org_id is None:
        raise MissingOrgIdError("org_id is required for llm_traces insert")
    if dsn is None or not dsn.strip():
        CLICKHOUSE_SKIP_COUNTER.labels(reason="empty_dsn").inc()
        logger.info("extraction_clickhouse_skipped", extra={"reason": "empty_dsn"})
        return False
    payload = _row_json(row)
    url, auth = _http_endpoint(dsn)
    own = client is None
    http = client or httpx.Client()
    try:
        response = http.post(
            url,
            params={"query": _INSERT_SQL},
            content=payload + "\n",
            headers={"Content-Type": "application/json"},
            auth=auth,
            timeout=5.0,
        )
        if response.status_code >= 400:
            CLICKHOUSE_SKIP_COUNTER.labels(reason="http_error").inc()
            logger.warning(
                "extraction_clickhouse_insert_failed",
                extra={"status_code": response.status_code},
            )
            return False
        return True
    except httpx.HTTPError:
        CLICKHOUSE_SKIP_COUNTER.labels(reason="http_error").inc()
        logger.warning("extraction_clickhouse_insert_failed", extra={"reason": "transport"})
        return False
    finally:
        if own:
            http.close()


def _row_json(row: ExtractionTraceRow) -> str:
    import json

    total = int(row.input_tokens) + int(row.output_tokens)
    assert row.org_id is not None
    body: dict[str, Any] = {
        "request_id": row.request_id,
        "org_id": str(row.org_id),
        "agent_id": str(row.agent_id),
        "session_id": str(row.session_id) if row.session_id else None,
        "checkpoint_id": None,
        "model": row.model,
        "provider": row.provider,
        "is_streaming": False,
        "input_tokens": int(row.input_tokens),
        "output_tokens": int(row.output_tokens),
        "total_tokens": total,
        "auth_latency_ms": 0,
        "directive_latency_ms": 0,
        "provider_ttfb_ms": int(row.provider_ttfb_ms),
        "total_latency_ms": int(row.total_latency_ms),
        "status_code": int(row.status_code),
        "is_complete": row.is_complete,
        "error_code": row.error_code,
        "requested_at": _ch_datetime(row.requested_at),
        "completed_at": _ch_datetime(row.completed_at),
    }
    return json.dumps(body)


def _ch_datetime(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _http_endpoint(dsn: str) -> tuple[str, tuple[str, str] | None]:
    parsed = urlparse(dsn)
    if parsed.scheme not in {"clickhouse", "http", "https"}:
        raise ValueError(f"unsupported ClickHouse DSN scheme: {parsed.scheme!r}")
    scheme = "https" if parsed.scheme == "https" or parsed.port == 8443 else "http"
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8123
    url = f"{scheme}://{host}:{port}/"
    auth = None
    if parsed.username is not None:
        auth = (parsed.username, parsed.password or "")
    return url, auth
