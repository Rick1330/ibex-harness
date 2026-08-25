"""Async audit emitter tests."""

from __future__ import annotations

import asyncio
from uuid import UUID

import pytest

from app.audit import AsyncAuditEmitter, MemoryAuditSink, ToolCallAuditEvent

ORG = UUID("11111111-1111-1111-1111-111111111111")


@pytest.mark.asyncio
async def test_emit_is_non_blocking() -> None:
    sink = MemoryAuditSink()
    emitter = AsyncAuditEmitter(sink, maxsize=8)
    emitter.start()
    for i in range(5):
        emitter.emit(
            ToolCallAuditEvent(
                request_id=f"r{i}",
                org_id=ORG,
                tool_name="search_memory",
                latency_ms=1,
                success=True,
            )
        )
    await asyncio.sleep(0.05)
    await emitter.aclose()
    assert len(sink.events) == 5
    assert all(e.org_id == ORG for e in sink.events)


@pytest.mark.asyncio
async def test_queue_full_drops() -> None:
    class SlowSink(MemoryAuditSink):
        async def write(self, event: ToolCallAuditEvent) -> None:
            await asyncio.sleep(0.2)
            await super().write(event)

    sink = SlowSink()
    emitter = AsyncAuditEmitter(sink, maxsize=1)
    emitter.start()
    emitter.emit(
        ToolCallAuditEvent(
            request_id="a",
            org_id=ORG,
            tool_name="search_memory",
            latency_ms=1,
            success=True,
        )
    )
    # Fill queue and force drops without blocking the caller.
    for i in range(5):
        emitter.emit(
            ToolCallAuditEvent(
                request_id=f"d{i}",
                org_id=ORG,
                tool_name="write_memory",
                latency_ms=1,
                success=True,
            )
        )
    await emitter.aclose()
