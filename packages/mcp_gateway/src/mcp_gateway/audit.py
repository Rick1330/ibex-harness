"""Metadata-only audit events and a non-blocking async emitter.

Audit must never block a read (AGENTS.md §6.1). The event carries the fields an
``evidence.tool_audit``-class row needs (principal, tool, descriptor hash, scope
outcome, decision, latency) but contains no payload content.

Two seams:

- ``AuditEmitter`` — what the enforcer calls (``emit`` is synchronous and must not
  block on I/O); satisfied by ``AsyncAuditEmitter``, ``InMemoryAuditEmitter``, and
  ``NullAuditEmitter``.
- ``AuditSink`` — the actual I/O target (log/ClickHouse) drained by the emitter,
  supplied by the deployable service.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ToolAuditEvent:
    request_id: str
    org_id: UUID
    tool_name: str
    decision: str
    success: bool
    latency_ms: int
    tool_version: str = ""
    descriptor_hash: str = ""
    scope: str = ""
    scope_ok: bool = False
    error_code: str = ""
    agent_id: UUID | None = None
    requested_at: datetime | None = None

    def normalized(self) -> ToolAuditEvent:
        when = self.requested_at or datetime.now(UTC)
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        return ToolAuditEvent(
            request_id=self.request_id,
            org_id=self.org_id,
            tool_name=self.tool_name,
            decision=self.decision,
            success=self.success,
            latency_ms=max(0, int(self.latency_ms)),
            tool_version=self.tool_version,
            descriptor_hash=self.descriptor_hash,
            scope=self.scope,
            scope_ok=self.scope_ok,
            error_code=self.error_code,
            agent_id=self.agent_id,
            requested_at=when,
        )

    def as_log_fields(self) -> dict[str, str]:
        event = self.normalized()
        return {
            "request_id": event.request_id,
            "org_id": str(event.org_id),
            "agent_id": str(event.agent_id) if event.agent_id is not None else "",
            "tool_name": event.tool_name,
            "tool_version": event.tool_version,
            "descriptor_hash": event.descriptor_hash,
            "scope": event.scope,
            "scope_ok": str(event.scope_ok),
            "decision": event.decision,
            "success": str(event.success),
            "error_code": event.error_code,
            "latency_ms": str(event.latency_ms),
        }

    def as_clickhouse_row(self) -> dict[str, object]:
        """Metadata-only row for ``ibex.mcp_tool_calls`` (no content columns).

        The rich fields (descriptor hash, scope, decision) are carried in
        structured logs; the shared ClickHouse audit table keeps its fixed
        schema. Durable rich-field persistence is a documented deferral.
        """
        event = self.normalized()
        when = event.requested_at
        if when is None:  # pragma: no cover - normalized() always sets it
            raise RuntimeError("audit requested_at missing")
        effective_error = event.error_code
        if event.decision == "deny" and not effective_error:
            effective_error = "permission_denied"
        return {
            "request_id": event.request_id,
            "org_id": str(event.org_id),
            "agent_id": str(event.agent_id) if event.agent_id is not None else None,
            "tool_name": event.tool_name or "unknown",
            "latency_ms": event.latency_ms,
            "success": event.success,
            "error_code": effective_error,
            "requested_at": when.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        }


class AuditEmitter(Protocol):
    """What the enforcer calls; ``emit`` must not block on I/O."""

    def emit(self, event: ToolAuditEvent) -> None: ...


class AuditSink(Protocol):
    """I/O target drained by ``AsyncAuditEmitter``."""

    name: str

    async def write(self, event: ToolAuditEvent) -> None: ...

    async def aclose(self) -> None: ...


class NullAuditEmitter:
    """Discards events; used when no audit sink is configured."""

    name = "null"

    def emit(self, event: ToolAuditEvent) -> None:
        _ = event


class InMemoryAuditEmitter:
    """Collects events in-process; used by tests and local runs."""

    name = "memory"

    def __init__(self) -> None:
        self.events: list[ToolAuditEvent] = []

    def emit(self, event: ToolAuditEvent) -> None:
        self.events.append(event.normalized())


class AsyncAuditEmitter:
    """Fire-and-forget queue; never blocks tool handlers on sink latency."""

    name = "async"

    def __init__(self, sink: AuditSink, *, maxsize: int = 1024) -> None:
        self._sink = sink
        self._queue: asyncio.Queue[ToolAuditEvent | None] = asyncio.Queue(maxsize=maxsize)
        self._task: asyncio.Task[None] | None = None
        self._closed = False
        self._dropped = 0

    @property
    def dropped(self) -> int:
        return self._dropped

    @property
    def sink_name(self) -> str:
        return getattr(self._sink, "name", "unknown")

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="mcp-operator-audit")

    def emit(self, event: ToolAuditEvent) -> None:
        if self._closed:
            self._dropped += 1
            return
        try:
            self._queue.put_nowait(event.normalized())
        except asyncio.QueueFull:
            self._dropped += 1
            logger.warning(
                "mcp operator audit queue full; dropping event tool_name=%s",
                event.tool_name,
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
            await asyncio.wait({task}, timeout=1.0)
        await self._sink.aclose()

    async def _signal_stop(self) -> None:
        for _ in range(3):
            try:
                self._queue.put_nowait(None)
                return
            except asyncio.QueueFull:
                try:
                    self._queue.get_nowait()
                    self._dropped += 1
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0)
        self._drain()
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            logger.warning("mcp operator audit shutdown could not enqueue sentinel")

    def _drain(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._dropped += 1
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
                logger.exception(
                    "mcp operator audit sink write failed sink=%s tool_name=%s",
                    self.sink_name,
                    item.tool_name,
                )


__all__ = [
    "AsyncAuditEmitter",
    "AuditEmitter",
    "AuditSink",
    "InMemoryAuditEmitter",
    "NullAuditEmitter",
    "ToolAuditEvent",
]
