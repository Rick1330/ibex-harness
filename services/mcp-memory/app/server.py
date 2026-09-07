"""FastMCP server with search_memory / write_memory tools (memory HTTP)."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated, Any
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import ConfigDict, Field

from app.audit import AsyncAuditEmitter, ToolCallAuditEvent
from app.clients.memory import MemoryHttpClient
from app.errors import MCPServiceError
from app.principal import require_principal
from app.tools import (
    Category,
    parse_search_args,
    parse_write_args,
)
from app.tools import (
    search_memory as run_search_memory,
)
from app.tools import (
    write_memory as run_write_memory,
)

logger = logging.getLogger(__name__)


def build_mcp_server(
    audit: AsyncAuditEmitter,
    memory_client: MemoryHttpClient | None,
    *,
    allow_test_hosts: bool = True,
) -> FastMCP:
    mcp = FastMCP(
        "ibex-mcp-memory",
        instructions=(
            "IBEX memory MCP resource server (G6.M1 / 3.5.E.2). "
            "search_memory and write_memory call the memory service over HTTP. "
            "Auth is required. Streamable HTTP is stateless (no EventStore resumability)."
        ),
        # Stateless + JSON responses: no session EventStore / resumable SSE
        # (explicitly out of scope for 3.5.E.1 — document in milestone MDX).
        stateless_http=True,
        json_response=True,
        transport_security=_transport_security(allow_test_hosts=allow_test_hosts),
    )

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
            audit=audit,
            tool_name="search_memory",
            raw=_optional_agent({"query": query, "limit": limit}, agent_id),
            runner=lambda raw: _run_search(raw, memory_client),
        )

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
            audit=audit,
            tool_name="write_memory",
            raw=_optional_agent(
                {"content": content, "category": category, "confidence": confidence},
                agent_id,
            ),
            runner=lambda raw: _run_write(raw, memory_client),
        )

    _forbid_undeclared_tool_args(mcp)
    return mcp


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
            allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://testserver"],
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


async def _invoke_tool(
    *,
    audit: AsyncAuditEmitter,
    tool_name: str,
    raw: dict[str, Any],
    runner: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
) -> str:
    started = time.perf_counter()
    request_id = str(uuid.uuid4())
    principal = require_principal()
    success = False
    error_code = ""
    try:
        result = await runner(raw)
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
    finally:
        latency_ms = int((time.perf_counter() - started) * 1000)
        audit.emit(
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
