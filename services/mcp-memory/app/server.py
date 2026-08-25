"""FastMCP server with stub search_memory / write_memory tools."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.audit import AsyncAuditEmitter, ToolCallAuditEvent
from app.errors import MCPServiceError
from app.principal import require_principal
from app.tools import (
    SEARCH_MEMORY_SCHEMA,
    WRITE_MEMORY_SCHEMA,
    parse_search_args,
    parse_write_args,
    stub_search_memory,
    stub_write_memory,
)

logger = logging.getLogger(__name__)


def build_mcp_server(audit: AsyncAuditEmitter, *, allow_test_hosts: bool = True) -> FastMCP:
    mcp = FastMCP(
        "ibex-mcp-memory",
        instructions=(
            "IBEX memory MCP resource server (G6.M1). "
            "Tools are stubs — no persistence. Auth is required."
        ),
        stateless_http=True,
        json_response=True,
        transport_security=_transport_security(allow_test_hosts=allow_test_hosts),
    )

    @mcp.tool(
        name="search_memory",
        description="Search org-scoped memories (stub — returns deterministic mock hits).",
    )
    async def search_memory(
        query: str,
        limit: int = 5,
        agent_id: str | None = None,
    ) -> str:
        return await _invoke_tool(
            audit=audit,
            tool_name="search_memory",
            raw=_optional_agent({"query": query, "limit": limit}, agent_id),
            runner=_run_search,
        )

    @mcp.tool(
        name="write_memory",
        description="Write an explicit memory (stub — does not persist).",
    )
    async def write_memory(
        content: str,
        category: str = "fact",
        confidence: float = 0.6,
        agent_id: str | None = None,
    ) -> str:
        return await _invoke_tool(
            audit=audit,
            tool_name="write_memory",
            raw=_optional_agent(
                {"content": content, "category": category, "confidence": confidence},
                agent_id,
            ),
            runner=_run_write,
        )

    search_memory.__mcp_schema__ = SEARCH_MEMORY_SCHEMA  # type: ignore[attr-defined]
    write_memory.__mcp_schema__ = WRITE_MEMORY_SCHEMA  # type: ignore[attr-defined]
    return mcp


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


def _optional_agent(payload: dict[str, Any], agent_id: str | None) -> dict[str, Any]:
    if agent_id is not None:
        return {**payload, "agent_id": agent_id}
    return payload


def _run_search(raw: dict[str, Any]) -> dict[str, Any]:
    return stub_search_memory(require_principal(), parse_search_args(raw))


def _run_write(raw: dict[str, Any]) -> dict[str, Any]:
    return stub_write_memory(require_principal(), parse_write_args(raw))


async def _invoke_tool(
    *,
    audit: AsyncAuditEmitter,
    tool_name: str,
    raw: dict[str, Any],
    runner: Callable[[dict[str, Any]], dict[str, Any]],
) -> str:
    started = time.perf_counter()
    request_id = str(uuid.uuid4())
    principal = require_principal()
    success = False
    error_code = ""
    try:
        result = runner(raw)
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
