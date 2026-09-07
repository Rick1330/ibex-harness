"""Rate-limit enforcement via _invoke_tool (isError / rate_limited contract)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pytest

from app.access_token import set_access_token
from app.audit import AsyncAuditEmitter, MemoryAuditSink
from app.errors import RateLimitedError
from app.permissions import MEMORY_READ, MEMORY_WRITE
from app.principal import Principal, set_principal
from app.ratelimit import McpRateLimiter, NoopMcpLimiter, RateLimitResult
from app.server import _invoke_tool, _ToolCall, _ToolRequest
from tests.memory_fixtures import AGENT, ORG


@dataclass
class _FixedLimiter(McpRateLimiter):
    allow: bool = True
    limit: int = 1

    async def check(self, org_id: UUID) -> RateLimitResult:
        del org_id
        return RateLimitResult(
            allowed=self.allow,
            limit=self.limit,
            remaining=0 if not self.allow else self.limit,
            reset_unix=0,
        )


@pytest.mark.asyncio
async def test_invoke_rate_limited_audited() -> None:
    sink = MemoryAuditSink()
    audit = AsyncAuditEmitter(sink, maxsize=8)
    audit.start()
    set_principal(Principal(org_id=ORG, permissions=MEMORY_READ | MEMORY_WRITE, agent_id=AGENT))
    set_access_token("tok")
    call = _ToolCall(
        audit=audit,
        rate_limiter=_FixedLimiter(allow=False),
        request=_ToolRequest(
            tool_name="search_memory",
            raw={"query": "x"},
            runner=lambda raw: _never(raw),
        ),
    )
    try:
        with pytest.raises(RateLimitedError) as exc_info:
            await _invoke_tool(call)
    finally:
        set_principal(None)
        set_access_token(None)
        await audit.aclose()
    assert exc_info.value.code == "rate_limited"
    assert len(sink.events) == 1
    assert sink.events[0].success is False
    assert sink.events[0].error_code == "rate_limited"


async def _never(_raw: dict) -> dict:
    raise AssertionError("runner must not run when rate limited")


@pytest.mark.asyncio
async def test_invoke_internal_error_audited() -> None:
    sink = MemoryAuditSink()
    audit = AsyncAuditEmitter(sink, maxsize=8)
    audit.start()
    set_principal(Principal(org_id=ORG, permissions=MEMORY_WRITE, agent_id=AGENT))
    set_access_token("tok")

    async def boom(_raw: dict) -> dict:
        raise RuntimeError("boom")

    call = _ToolCall(
        audit=audit,
        rate_limiter=NoopMcpLimiter(),
        request=_ToolRequest(
            tool_name="search_memory",
            raw={"query": "x"},
            runner=boom,
        ),
    )
    try:
        with pytest.raises(RuntimeError, match="boom"):
            await _invoke_tool(call)
    finally:
        set_principal(None)
        set_access_token(None)
        await audit.aclose()
    assert sink.events[0].error_code == "internal_error"
    assert sink.events[0].success is False
