"""Audit sinks for the operator gateway (metadata only, never content).

Reuses the shared ``ibex.mcp_tool_calls`` ClickHouse table (same schema as
``services/mcp-memory``). The rich fields (descriptor hash, scope, decision) are
carried in structured logs; durable rich-field persistence is a documented
deferral. The default sink is logging-only unless a ClickHouse URL is configured.
"""

from __future__ import annotations

import logging
from urllib.parse import SplitResult, unquote, urlsplit, urlunsplit

import httpx
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
        logger.info("mcp_operator_tool_call", extra=event.as_log_fields())

    async def aclose(self) -> None:  # NOSONAR python:S7503 - AuditSink lifecycle contract
        return None


class ClickHouseOperatorAuditSink:
    """Inserts ``ibex.mcp_tool_calls`` rows via ClickHouse HTTP (JSONEachRow)."""

    name = "clickhouse"

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 2.0,
        mirror: AuditSink | None = None,
    ) -> None:
        self._base_url, self._auth = _split_base_url(base_url)
        self._client = httpx.AsyncClient(timeout=timeout_seconds)
        self._mirror = mirror or LoggingOperatorAuditSink()

    async def write(self, event: ToolAuditEvent) -> None:
        await self._mirror.write(event)
        row = event.as_clickhouse_row()
        try:
            response = await self._client.post(
                self._base_url,
                params={"query": _INSERT_QUERY},
                json=row,
                auth=self._auth,
            )
        except Exception:  # noqa: BLE001 - never surface a URL that may carry credentials
            raise RuntimeError("clickhouse audit write failed") from None
        if response.status_code >= 400:
            raise RuntimeError(f"clickhouse audit write failed status={response.status_code}")

    async def aclose(self) -> None:
        await self._mirror.aclose()
        await self._client.aclose()


def _split_base_url(url: str) -> tuple[str, httpx.BasicAuth | None]:
    parts = _validated_url(url)
    netloc = _netloc(parts)
    auth = _basic_auth(parts)
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, "")), auth


def _validated_url(url: str) -> SplitResult:
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("clickhouse URL must be http(s) with a host")
    has_credentials = parts.username is not None or parts.password is not None
    is_local = parts.hostname in {"localhost", "127.0.0.1", "::1"}
    if parts.scheme == "http" and has_credentials and not is_local:
        raise ValueError("clickhouse credentials require HTTPS outside local development")
    return parts


def _netloc(parts: SplitResult) -> str:
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    return host if parts.port is None else f"{host}:{parts.port}"


def _basic_auth(parts: SplitResult) -> httpx.BasicAuth | None:
    if parts.username is None and parts.password is None:
        return None
    return httpx.BasicAuth(unquote(parts.username or ""), unquote(parts.password or ""))


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
