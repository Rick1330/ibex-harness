"""FastMCP server with search_memory / write_memory / record_feedback tools."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import ConfigDict, Field

from app.audit import AsyncAuditEmitter, ToolCallAuditEvent
from app.clients.memory import MemoryHttpClient
from app.errors import MCPServiceError, RateLimitedError
from app.principal import require_principal
from app.ratelimit import McpRateLimiter, NoopMcpLimiter
from app.tools import (
    Category,
    FeedbackKind,
    parse_feedback_args,
    parse_search_args,
    parse_write_args,
)
from app.tools import (
    record_feedback as run_record_feedback,
)
from app.tools import (
    search_memory as run_search_memory,
)
from app.tools import (
    write_memory as run_write_memory,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _ToolRequest:
    tool_name: str
    raw: dict[str, Any]
    runner: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class _ToolCall:
    audit: AsyncAuditEmitter
    rate_limiter: McpRateLimiter
    request: _ToolRequest


def build_mcp_server(
    audit: AsyncAuditEmitter,
    memory_client: MemoryHttpClient | None,
    *,
    rate_limiter: McpRateLimiter | None = None,
    allow_test_hosts: bool = True,
) -> FastMCP:
    limiter = rate_limiter or NoopMcpLimiter()
    mcp = FastMCP(
        "ibex-mcp-memory",
        instructions=(
            "IBEX memory MCP resource server (G6.M1 / 3.5.E.2–E.4). "
            "search_memory, write_memory, and record_feedback call the memory "
            "service over HTTP. Auth is required. Streamable HTTP is stateless "
            "(no EventStore resumability)."
        ),
        # Stateless + JSON responses: no session EventStore / resumable SSE
        # (explicitly out of scope for 3.5.E.1 — document in milestone MDX).
        stateless_http=True,
        json_response=True,
        transport_security=_transport_security(allow_test_hosts=allow_test_hosts),
    )
    _register_search_tool(mcp, audit, memory_client, limiter)
    _register_write_tool(mcp, audit, memory_client, limiter)
    _register_feedback_tool(mcp, audit, memory_client, limiter)
    _forbid_undeclared_tool_args(mcp)
    return mcp


def _register_search_tool(
    mcp: FastMCP,
    audit: AsyncAuditEmitter,
    memory_client: MemoryHttpClient | None,
    limiter: McpRateLimiter,
) -> None:
    @mcp.tool(
        name="search_memory",
        description="Search org-scoped memories via the memory service HTTP API.",
    )
    async def search_memory(
        query: Annotated[str, Field(min_length=1, max_length=2000)],
        limit: Annotated[int, Field(default=5, ge=1, le=50)] = 5,
        agent_id: UUID | None = None,
    ) -> str:
        return await _invoke_tool(
            _ToolCall(
                audit=audit,
                rate_limiter=limiter,
                request=_ToolRequest(
                    tool_name="search_memory",
                    raw=_optional_agent({"query": query, "limit": limit}, agent_id),
                    runner=lambda raw: _run_search(raw, memory_client),
                ),
            )
        )


def _register_write_tool(
    mcp: FastMCP,
    audit: AsyncAuditEmitter,
    memory_client: MemoryHttpClient | None,
    limiter: McpRateLimiter,
) -> None:
    @mcp.tool(
        name="write_memory",
        description=(
            "Write an explicit memory through the memory service pipeline "
            "(metadata.mcp_source=mcp_explicit)."
        ),
    )
    async def write_memory(
        content: Annotated[str, Field(min_length=1, max_length=8000)],
        category: Category = "factual",
        confidence: Annotated[float, Field(default=0.6, ge=0.0, le=1.0)] = 0.6,
        agent_id: UUID | None = None,
    ) -> str:
        return await _invoke_tool(
            _ToolCall(
                audit=audit,
                rate_limiter=limiter,
                request=_ToolRequest(
                    tool_name="write_memory",
                    raw=_optional_agent(
                        {
                            "content": content,
                            "category": category,
                            "confidence": confidence,
                        },
                        agent_id,
                    ),
                    runner=lambda raw: _run_write(raw, memory_client),
                ),
            )
        )


def _register_feedback_tool(
    mcp: FastMCP,
    audit: AsyncAuditEmitter,
    memory_client: MemoryHttpClient | None,
    limiter: McpRateLimiter,
) -> None:
    @mcp.tool(
        name="record_feedback",
        description=(
            "Record positive/negative/neutral usefulness feedback for a memory "
            "via POST /v1/memories/{id}/feedback."
        ),
    )
    async def record_feedback(
        memory_id: UUID,
        feedback: FeedbackKind,
        session_id: UUID | None = None,
        trace_id: UUID | None = None,
        notes: Annotated[str | None, Field(default=None, max_length=2000)] = None,
    ) -> str:
        raw: dict[str, Any] = {"memory_id": str(memory_id), "feedback": feedback}
        if session_id is not None:
            raw["session_id"] = str(session_id)
        if trace_id is not None:
            raw["trace_id"] = str(trace_id)
        if notes is not None:
            raw["notes"] = notes
        return await _invoke_tool(
            _ToolCall(
                audit=audit,
                rate_limiter=limiter,
                request=_ToolRequest(
                    tool_name="record_feedback",
                    raw=raw,
                    runner=lambda payload: _run_feedback(payload, memory_client),
                ),
            )
        )


def _forbid_undeclared_tool_args(mcp: FastMCP) -> None:
    """Reject unknown tool arguments and advertise additionalProperties: false."""
    for tool in mcp._tool_manager._tools.values():
        model = tool.fn_metadata.arg_model
        type.__setattr__(
            model,
            "model_config",
            ConfigDict(arbitrary_types_allowed=True, extra="forbid"),
        )
        model.model_rebuild(force=True)
        schema = model.model_json_schema(by_alias=True)
        schema["additionalProperties"] = False
        tool.parameters = schema


def _transport_security(*, allow_test_hosts: bool) -> TransportSecuritySettings:
    if allow_test_hosts:
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
            allowed_hosts=["127.0.0.1:*", "localhost:*", "testserver", "testserver:*"],
            allowed_origins=[
                "http://127.0.0.1:*",
                "http://localhost:*",
                "http://testserver",
            ],
        )
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[],
        allowed_origins=[],
    )


def _optional_agent(payload: dict[str, Any], agent_id: UUID | None) -> dict[str, Any]:
    if agent_id is not None:
        return {**payload, "agent_id": str(agent_id)}
    return payload


async def _run_search(
    raw: dict[str, Any], client: MemoryHttpClient | None
) -> dict[str, Any]:
    return await run_search_memory(require_principal(), parse_search_args(raw), client)


async def _run_write(
    raw: dict[str, Any], client: MemoryHttpClient | None
) -> dict[str, Any]:
    return await run_write_memory(require_principal(), parse_write_args(raw), client)


async def _run_feedback(
    raw: dict[str, Any], client: MemoryHttpClient | None
) -> dict[str, Any]:
    return await run_record_feedback(
        require_principal(), parse_feedback_args(raw), client
    )


async def _invoke_tool(call: _ToolCall) -> str:
    started = time.perf_counter()
    request_id = str(uuid.uuid4())
    principal = require_principal()
    success = False
    error_code = ""
    tool_name = call.request.tool_name
    try:
        decision = await call.rate_limiter.check(principal.org_id)
        if not decision.allowed:
            raise RateLimitedError()
        result = await call.request.runner(call.request.raw)
        success = True
        return json.dumps(result, separators=(",", ":"), sort_keys=True)
    except MCPServiceError as exc:
        error_code = exc.code
        logger.info(
            "mcp tool failed tool_name=%s error_code=%s request_id=%s",
            tool_name,
            exc.code,
            request_id,
        )
        raise
    except Exception:
        error_code = "internal_error"
        logger.exception(
            "mcp tool internal_error tool_name=%s request_id=%s",
            tool_name,
            request_id,
        )
        raise
    finally:
        latency_ms = int((time.perf_counter() - started) * 1000)
        call.audit.emit(
            ToolCallAuditEvent(
                request_id=request_id,
                org_id=principal.org_id,
                agent_id=principal.agent_id,
                tool_name=tool_name,
                latency_ms=latency_ms,
                success=success,
                error_code=error_code,
            )
        )
