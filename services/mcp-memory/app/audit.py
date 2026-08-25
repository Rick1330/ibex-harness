"""Async non-blocking MCP tool-call audit emitter (ClickHouse-compatible)."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from prometheus_client import Counter

logger = logging.getLogger(__name__)

AUDIT_DROPPED = Counter(
    "ibex_mcp_audit_dropped_total",
    "MCP audit events dropped because the async queue was full",
)
AUDIT_EMITTED = Counter(
    "ibex_mcp_audit_emitted_total",
    "MCP audit events successfully written",
    ["sink"],
)
AUDIT_SINK_ERRORS = Counter(
    "ibex_mcp_audit_sink_errors_total",
    "MCP audit sink write failures",
    ["sink"],
)

_INSERT_QUERY = (
    "INSERT INTO ibex.mcp_tool_calls "
    "(request_id, org_id, agent_id, tool_name, latency_ms, success, error_code, requested_at) "
    "FORMAT JSONEachRow"
)


@dataclass(frozen=True, slots=True)
class ToolCallAuditEvent:
    request_id: str
    org_id: UUID
    tool_name: str
    latency_ms: int
    success: bool
    error_code: str = ""
    agent_id: UUID | None = None
    requested_at: datetime | None = None

    def normalized(self) -> ToolCallAuditEvent:
        when = self.requested_at or datetime.now(UTC)
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        return ToolCallAuditEvent(
            request_id=self.request_id,
            org_id=self.org_id,
            tool_name=self.tool_name,
            latency_ms=max(0, int(self.latency_ms)),
            success=self.success,
            error_code=self.error_code or "",
            agent_id=self.agent_id,
            requested_at=when,
        )

    def as_clickhouse_row(self) -> dict[str, Any]:
        """Metadata-only row matching ibex.mcp_tool_calls (no content columns)."""
        event = self.normalized()
        when = event.requested_at
        if when is None:
            raise RuntimeError("audit requested_at missing")
        return {
            "request_id": event.request_id,
            "org_id": str(event.org_id),
            "agent_id": str(event.agent_id) if event.agent_id is not None else None,
            "tool_name": event.tool_name,
            "latency_ms": event.latency_ms,
            "success": event.success,
            "error_code": event.error_code,
            "requested_at": when.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        }


class AuditSink(ABC):
    name: str = "abstract"

    @abstractmethod
    async def write(self, event: ToolCallAuditEvent) -> None:
        raise NotImplementedError

    async def aclose(self) -> None:
        client = getattr(self, "_client", None)
        if client is None:
            return
        await client.aclose()


class MemoryAuditSink(AuditSink):
    """Records events in-process for tests."""

    name = "memory"

    def __init__(self) -> None:
        self.events: list[ToolCallAuditEvent] = []

    async def write(self, event: ToolCallAuditEvent) -> None:
        self.events.append(event)
        AUDIT_EMITTED.labels(sink=self.name).inc()


class LoggingAuditSink(AuditSink):
    """Dev fallback when ClickHouse URL is unset — metadata only, never content."""

    name = "log"

    async def write(self, event: ToolCallAuditEvent) -> None:
        logger.info(
            "mcp_tool_call request_id=%s org_id=%s tool_name=%s latency_ms=%d success=%s error_code=%s",
            event.request_id,
            event.org_id,
            event.tool_name,
            event.latency_ms,
            event.success,
            event.error_code or "",
        )
        AUDIT_EMITTED.labels(sink=self.name).inc()


class ClickHouseHTTPAuditSink(AuditSink):
    """Inserts mcp_tool_calls rows via ClickHouse HTTP (JSONEachRow)."""

    name = "clickhouse"

    def __init__(self, base_url: str, *, timeout_seconds: float = 2.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def write(self, event: ToolCallAuditEvent) -> None:
        row = event.as_clickhouse_row()
        response = await self._client.post(
            self._base_url,
            params={"query": _INSERT_QUERY},
            json=row,
        )
        response.raise_for_status()
        AUDIT_EMITTED.labels(sink=self.name).inc()


def build_audit_sink(clickhouse_url: str) -> AuditSink:
    url = clickhouse_url.strip()
    if not url:
        return LoggingAuditSink()
    return ClickHouseHTTPAuditSink(url)


class AsyncAuditEmitter:
    """Fire-and-forget queue; never blocks tool handlers on sink latency."""

    def __init__(self, sink: AuditSink, *, maxsize: int = 1024) -> None:
        self._sink = sink
        self._queue: asyncio.Queue[ToolCallAuditEvent | None] = asyncio.Queue(maxsize=maxsize)
        self._task: asyncio.Task[None] | None = None
        self._closed = False

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="mcp-audit-emitter")

    def emit(self, event: ToolCallAuditEvent) -> None:
        if self._closed:
            AUDIT_DROPPED.inc()
            return
        normalized = event.normalized()
        try:
            self._queue.put_nowait(normalized)
        except asyncio.QueueFull:
            AUDIT_DROPPED.inc()
            logger.warning(
                "mcp audit queue full; dropping event tool_name=%s",
                normalized.tool_name,
            )

    async def aclose(self) -> None:
        self._closed = True
        task = self._task
        self._task = None
        if task is None:
            await self._sink.aclose()
            return
        await self._signal_stop()
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except TimeoutError:
            task.cancel()
            # wait() does not raise CancelledError for the cancelled child task.
            await asyncio.wait({task}, timeout=1.0)
        await self._sink.aclose()

    async def _signal_stop(self) -> None:
        """Enqueue sentinel without blocking forever on a saturated queue."""
        if await self._try_enqueue_sentinel(attempts=3):
            return
        self._drain_queue()
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            logger.warning("mcp audit shutdown could not enqueue sentinel")

    async def _try_enqueue_sentinel(self, *, attempts: int) -> bool:
        for _ in range(attempts):
            try:
                self._queue.put_nowait(None)
                return True
            except asyncio.QueueFull:
                try:
                    self._queue.get_nowait()
                    AUDIT_DROPPED.inc()
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0)
        return False

    def _drain_queue(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                AUDIT_DROPPED.inc()
            except asyncio.QueueEmpty:
                break

    async def _run(self) -> None:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            try:
                await self._sink.write(item)
            except Exception:
                AUDIT_SINK_ERRORS.labels(sink=getattr(self._sink, "name", "unknown")).inc()
                logger.exception(
                    "mcp audit sink write failed tool_name=%s",
                    item.tool_name,
                )
