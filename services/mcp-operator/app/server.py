"""FastMCP surface for the read-only operator gateway.

Each tool routes through the shared enforcement pipeline
(``mcp_gateway.GatewayEnforcer``); the published JSON Schema is overwritten with
the registry's canonical ``input_schema`` so the advertised surface is exactly
the descriptor that is hashed for identity binding.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Annotated, Any
from urllib.parse import urlsplit
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp_gateway import GatewayEnforcer, GatewayError, ToolRegistry
from pydantic import ConfigDict, Field

from app.errors import to_tool_call_error
from app.principal import require_principal
from app.tools import BUDGET_MAX_LIMIT, EVIDENCE_MAX_LIMIT

_SERVER_INSTRUCTIONS = (
    "IBEX read-only operator MCP gateway (GAP-009). Four read tools return "
    "redacted, org-scoped metadata only; every call is authorized by the verified "
    "token's permission bitmap and audited. Streamable HTTP is stateless."
)


@dataclass(frozen=True, slots=True)
class McpServerWiring:
    enforcer: GatewayEnforcer
    registry: ToolRegistry
    allow_test_hosts: bool = True
    resource_url: str = ""


def build_mcp_server(wiring: McpServerWiring) -> FastMCP:
    mcp = FastMCP(
        "ibex-mcp-operator",
        instructions=_SERVER_INSTRUCTIONS,
        stateless_http=True,
        json_response=True,
        transport_security=_transport_security(
            allow_test_hosts=wiring.allow_test_hosts,
            resource_url=wiring.resource_url,
        ),
    )
    _register_tools(mcp, wiring.enforcer)
    bind_declared_schemas(mcp, wiring.registry)
    return mcp


def bind_declared_schemas(mcp: FastMCP, registry: ToolRegistry) -> None:
    """Advertise the registry's canonical input schema for every tool."""
    for name, tool in mcp._tool_manager._tools.items():
        spec = registry.get(name)
        if spec is None:
            continue
        model = tool.fn_metadata.arg_model
        type.__setattr__(
            model,
            "model_config",
            ConfigDict(arbitrary_types_allowed=True, extra="forbid"),
        )
        model.model_rebuild(force=True)
        tool.parameters = spec.input_schema


def _register_tools(mcp: FastMCP, enforcer: GatewayEnforcer) -> None:
    @mcp.tool(
        name="session.get",
        description="Return redacted metadata for one session in the caller's org.",
    )
    async def session_get(session_id: UUID) -> str:
        return await _invoke(enforcer, "session.get", {"session_id": session_id})

    @mcp.tool(
        name="run.get",
        description="Return redacted metadata for one evidence run in the caller's org.",
    )
    async def run_get(run_id: UUID) -> str:
        return await _invoke(enforcer, "run.get", {"run_id": run_id})

    @mcp.tool(
        name="evidence.query",
        description="List redacted evidence-run metadata in the caller's org.",
    )
    async def evidence_query(
        trace_id: str | None = None,
        session_id: UUID | None = None,
        request_id: Annotated[str | None, Field(default=None, max_length=128)] = None,
        error_code: Annotated[str | None, Field(default=None, max_length=64)] = None,
        status: str | None = None,
        limit: Annotated[int, Field(default=25, ge=1, le=EVIDENCE_MAX_LIMIT)] = 25,
    ) -> str:
        return await _invoke(
            enforcer,
            "evidence.query",
            {
                "trace_id": trace_id,
                "session_id": session_id,
                "request_id": request_id,
                "error_code": error_code,
                "status": status,
                "limit": limit,
            },
        )

    @mcp.tool(
        name="budget.get",
        description="Return billing budget periods for the caller's org (cached cents).",
    )
    async def budget_get(
        active_only: bool = True,
        limit: Annotated[int, Field(default=20, ge=1, le=BUDGET_MAX_LIMIT)] = 20,
    ) -> str:
        return await _invoke(enforcer, "budget.get", {"active_only": active_only, "limit": limit})


async def _invoke(enforcer: GatewayEnforcer, tool_name: str, raw: dict[str, Any]) -> str:
    principal = require_principal()
    try:
        result = await enforcer.invoke(
            principal,
            tool_name,
            raw,
            request_id=str(uuid.uuid4()),
        )
    except GatewayError as exc:
        raise to_tool_call_error(exc) from exc
    return json.dumps(result, separators=(",", ":"), sort_keys=True)


def _transport_security(
    *, allow_test_hosts: bool, resource_url: str = ""
) -> TransportSecuritySettings:
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
        allowed_hosts=_allowed_hosts(resource_url),
        allowed_origins=[],
    )


def _allowed_hosts(resource_url: str) -> list[str]:
    """Derive Host allowlist entries from the advertised resource URL.

    An empty allowlist with protection enabled rejects every request (421), so
    production fails closed for an unconfigured host rather than silently
    accepting any Host header. Both bare-host and wildcard-port forms are
    accepted because proxies vary in whether they preserve the port.
    """
    netloc = urlsplit(resource_url.strip()).netloc.lower()
    if not netloc:
        return []
    hostname = netloc.rsplit("@", 1)[-1].rsplit(":", 1)[0]
    hosts = [netloc]
    if hostname:
        hosts.append(f"{hostname}:*")
    return list(dict.fromkeys(hosts))
