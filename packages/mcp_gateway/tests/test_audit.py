"""Non-blocking audit emitter tests."""

from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import uuid4

from support import SampleArgs  # noqa: F401  (keeps support importable in test path)

from mcp_gateway.audit import (
    AsyncAuditEmitter,
    InMemoryAuditEmitter,
    NullAuditEmitter,
    ToolAuditEvent,
)


def _event(**overrides) -> ToolAuditEvent:
    base = {
        "request_id": "req-1",
        "org_id": uuid4(),
        "tool_name": "sample.get",
        "decision": "allow",
        "success": True,
        "latency_ms": 5,
    }
    base.update(overrides)
    return ToolAuditEvent(**base)


def test_null_emitter_is_inert() -> None:
    NullAuditEmitter().emit(_event())


def test_in_memory_emitter_normalizes() -> None:
    emitter = InMemoryAuditEmitter()
    emitter.emit(_event(latency_ms=-3, requested_at=datetime(2026, 1, 1)))
    assert emitter.events[0].latency_ms == 0
    assert emitter.events[0].requested_at is not None


def test_log_fields_and_clickhouse_row() -> None:
    event = _event(decision="deny", error_code="permission_denied", descriptor_hash="sha256:x")
    fields = event.as_log_fields()
    assert fields["decision"] == "deny"
    assert fields["descriptor_hash"] == "sha256:x"
    row = event.as_clickhouse_row()
    assert row["tool_name"] == "sample.get"
    assert row["error_code"] == "permission_denied"
    assert isinstance(row["requested_at"], str)


def test_clickhouse_row_defaults_deny_error_code() -> None:
    row = _event(decision="deny", error_code="").as_clickhouse_row()
    assert row["error_code"] == "permission_denied"


async def test_async_emitter_drains_to_sink_and_closes() -> None:
    class _Sink:
        name = "test"

        def __init__(self) -> None:
            self.events: list[ToolAuditEvent] = []
            self.closed = False

        async def write(self, event: ToolAuditEvent) -> None:
            self.events.append(event)

        async def aclose(self) -> None:
            self.closed = True

    sink = _Sink()
    emitter = AsyncAuditEmitter(sink, maxsize=8)
    emitter.start()
    for _ in range(5):
        emitter.emit(_event())
    await asyncio.sleep(0.05)
    await emitter.aclose()
    assert len(sink.events) == 5
    assert sink.closed is True
    assert emitter.dropped == 0


async def test_async_emitter_drops_when_full_and_closed() -> None:
    class _SlowSink:
        name = "slow"

        async def write(self, event: ToolAuditEvent) -> None:
            await asyncio.sleep(10)

        async def aclose(self) -> None:
            return None

    emitter = AsyncAuditEmitter(_SlowSink(), maxsize=1)
    emitter.start()
    for _ in range(5):
        emitter.emit(_event())
    assert emitter.dropped > 0
    emitter.emit(_event())
    await emitter.aclose()
