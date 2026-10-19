"""Audit sinks for the operator gateway (metadata only, never content).

Reuses the shared ``ibex.mcp_tool_calls`` ClickHouse table (same schema as
``services/mcp-memory``). The rich fields (descriptor hash, scope, decision) are
carried in structured logs; durable rich-field persistence is a documented
deferral. The default sink is logging-only unless a ClickHouse URL is configured.
"""

from __future__ import annotations

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

    async def write(self, event: ToolAuditEvent) -> None:
        fields = event.as_log_fields()
        logger.info(
            "mcp_operator_tool_call request_id=%s org_id=%s agent_id=%s tool_name=%s "
            "tool_version=%s descriptor_hash=%s scope=%s scope_ok=%s decision=%s "
            "success=%s error_code=%s latency_ms=%s",
            fields["request_id"],
            fields["org_id"],
            fields["agent_id"],
            fields["tool_name"],
            fields["tool_version"],
            fields["descriptor_hash"],
            fields["scope"],
            fields["scope_ok"],
            fields["decision"],
            fields["success"],
            fields["error_code"],
            fields["latency_ms"],
        )

    async def aclose(self) -> None:
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
        response = await self._client.post(
            self._base_url,
            params={"query": _INSERT_QUERY},
            json=row,
        )
        response.raise_for_status()

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
