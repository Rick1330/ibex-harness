"""Audit sinks for the operator gateway (metadata only, never content).

Reuses the shared ``ibex.mcp_tool_calls`` ClickHouse table (same schema as
``services/mcp-memory``). The rich fields (descriptor hash, scope, decision) are
carried in structured logs; durable rich-field persistence is a documented
deferral. The default sink is logging-only unless a ClickHouse URL is configured.
"""

from __future__ import annotations

import json
import logging

from mcp_gateway import AuditSink, ToolAuditEvent
from mcp_gateway.audit import AsyncAuditEmitter

logger = logging.getLogger(__name__)

_INSERT_QUERY = (
    "INSERT INTO ibex.mcp_tool_calls "
    "(request_id, org_id, agent_id, tool_name, latency_ms, success, error_code, requested_at) "
    "FORMAT JSONEachRow"
)


class LoggingOperatorAuditSink:
    """Dev fallback: metadata + rich fields in structured logs, never content."""

    name = "log"

    async def write(  # NOSONAR python:S7503 - async contract required by AuditSink
        self, event: ToolAuditEvent
    ) -> None:
        logger.info(json.dumps({"event": "mcp_operator_tool_call", **event.as_log_fields()}))

    async def aclose(self) -> None:  # NOSONAR python:S7503 - AuditSink lifecycle contract
        return None


class ClickHouseOperatorAuditSink:
    """Inserts ``ibex.mcp_tool_calls`` rows via ClickHouse HTTP (JSONEachRow)."""

    name = "clickhouse"

    def __init__(self, base_url: str, *, timeout_seconds: float = 2.0) -> None:
        import httpx

        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def write(self, event: ToolAuditEvent) -> None:
        row = event.as_clickhouse_row()
        try:
            response = await self._client.post(
                self._base_url,
                params={"query": _INSERT_QUERY},
                json=row,
            )
        except Exception:  # noqa: BLE001 - never surface a URL that may carry credentials
            raise RuntimeError("clickhouse audit write failed") from None
        if response.status_code >= 400:
            raise RuntimeError(f"clickhouse audit write failed status={response.status_code}")

    async def aclose(self) -> None:
        await self._client.aclose()


def build_operator_audit_sink(clickhouse_url: str) -> AuditSink:
    url = clickhouse_url.strip()
    if not url:
        return LoggingOperatorAuditSink()
    return ClickHouseOperatorAuditSink(url)


__all__ = [
    "AsyncAuditEmitter",
    "ClickHouseOperatorAuditSink",
    "LoggingOperatorAuditSink",
    "build_operator_audit_sink",
]
