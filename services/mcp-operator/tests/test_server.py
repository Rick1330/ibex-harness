"""FastMCP surface: schema binding, redaction, deny paths, audit."""

from __future__ import annotations

import json
from typing import Any

import pytest
from mcp_gateway import (
    BitmapPolicyEvaluator,
    GatewayEnforcer,
    GatewayPrincipal,
    InMemoryAuditEmitter,
)

from app.principal import set_principal
from app.server import McpServerWiring, _allowed_hosts, _transport_security, build_mcp_server
from app.tools import build_registry
from tests.fixtures import (
    AGENT,
    ORG,
    RUN_ID,
    SESSION_ID,
    StaticRateLimiter,
    stub_executor,
)


def _build(*, executor: Any = None, rate_limiter: Any = None, audit: Any = None):
    registry = build_registry()
    enforcer = GatewayEnforcer(
        registry,
        executor if executor is not None else stub_executor(),
        policy=BitmapPolicyEvaluator(),
        rate_limiter=rate_limiter or StaticRateLimiter(),
        audit=audit or InMemoryAuditEmitter(),
    )
    mcp = build_mcp_server(McpServerWiring(enforcer=enforcer, registry=registry))
    return mcp, registry


def _tool_fn(mcp: Any, name: str):
    return mcp._tool_manager._tools[name].fn


@pytest.mark.asyncio
async def test_published_schema_matches_registry_descriptor() -> None:
    mcp, registry = _build()
    listed = {spec.name: spec for spec in registry.specs()}
    for tool in await mcp.list_tools():
        spec = listed[tool.name]
        assert tool.inputSchema == spec.input_schema
        assert tool.inputSchema["additionalProperties"] is False


@pytest.mark.asyncio
async def test_all_four_tools_are_published() -> None:
    mcp, _ = _build()
    names = {tool.name for tool in await mcp.list_tools()}
    assert names == {"session.get", "run.get", "evidence.query", "budget.get"}


@pytest.mark.asyncio
async def test_session_get_redacts_undeclared_fields() -> None:
    audit = InMemoryAuditEmitter()
    mcp, _ = _build(audit=audit)
    fn = _tool_fn(mcp, "session.get")
    set_principal(GatewayPrincipal(org_id=ORG, permissions=(1 << 19), agent_id=AGENT))
    try:
        raw = await fn(session_id=SESSION_ID)
    finally:
        set_principal(None)
    payload = json.loads(raw)
    assert payload["session_id"] == str(SESSION_ID)
    assert "secret_content" not in payload
    assert len(audit.events) == 1
    assert audit.events[0].tool_name == "session.get"
    assert audit.events[0].success is True
    assert audit.events[0].decision == "allow"


@pytest.mark.asyncio
async def test_permission_denied_surfaces_typed_code() -> None:
    from app.errors import ToolCallError

    mcp, _ = _build()
    fn = _tool_fn(mcp, "session.get")
    set_principal(GatewayPrincipal(org_id=ORG, permissions=0, agent_id=AGENT))
    try:
        with pytest.raises(ToolCallError) as excinfo:
            await fn(session_id=SESSION_ID)
    finally:
        set_principal(None)
    assert excinfo.value.code == "permission_denied"
    assert str(excinfo.value).startswith("permission_denied:")


@pytest.mark.asyncio
async def test_invalid_params_surface_typed_code() -> None:
    from app.errors import ToolCallError

    mcp, _ = _build()
    fn = _tool_fn(mcp, "session.get")
    set_principal(GatewayPrincipal(org_id=ORG, permissions=(1 << 19), agent_id=AGENT))
    try:
        with pytest.raises(ToolCallError) as excinfo:
            await fn(session_id="not-a-uuid")
    finally:
        set_principal(None)
    assert excinfo.value.code == "invalid_params"


@pytest.mark.asyncio
async def test_not_found_surfaces_typed_code() -> None:
    from app.errors import ToolCallError

    mcp, _ = _build(executor=stub_executor({}))
    fn = _tool_fn(mcp, "run.get")
    set_principal(GatewayPrincipal(org_id=ORG, permissions=(1 << 24), agent_id=AGENT))
    try:
        with pytest.raises(ToolCallError) as excinfo:
            await fn(run_id=RUN_ID)
    finally:
        set_principal(None)
    assert excinfo.value.code == "not_found"


@pytest.mark.asyncio
async def test_rate_limited_surfaces_typed_code() -> None:
    from app.errors import ToolCallError

    mcp, _ = _build(rate_limiter=StaticRateLimiter(allowed=False))
    fn = _tool_fn(mcp, "budget.get")
    set_principal(GatewayPrincipal(org_id=ORG, permissions=(1 << 33), agent_id=AGENT))
    try:
        with pytest.raises(ToolCallError) as excinfo:
            await fn(active_only=True, limit=5)
    finally:
        set_principal(None)
    assert excinfo.value.code == "rate_limited"


@pytest.mark.asyncio
async def test_call_tool_smoke() -> None:
    mcp, _ = _build()
    set_principal(GatewayPrincipal(org_id=ORG, permissions=(1 << 19), agent_id=AGENT))
    try:
        result = await mcp.call_tool("session.get", {"session_id": str(SESSION_ID)})
    finally:
        set_principal(None)
    assert result is not None


def test_production_transport_security_derives_allowed_host() -> None:
    settings = _transport_security(
        allow_test_hosts=False, resource_url="https://mcp.example.com/mcp"
    )
    assert settings.enable_dns_rebinding_protection is True
    assert settings.allowed_hosts == ["mcp.example.com", "mcp.example.com:*"]
    assert settings.allowed_origins == []


def test_production_transport_security_fails_closed_without_host() -> None:
    settings = _transport_security(allow_test_hosts=False, resource_url="")
    assert settings.allowed_hosts == []


def test_allowed_hosts_handles_ports_and_ipv6() -> None:
    assert _allowed_hosts("https://MCP.example.com:8443/mcp") == [
        "mcp.example.com:8443",
        "mcp.example.com:*",
    ]
    assert _allowed_hosts("https://[::1]:8443/mcp") == ["[::1]:8443", "[::1]:*"]


@pytest.mark.asyncio
async def test_invalid_uuid_reaches_gateway_typed_error() -> None:
    from app.errors import ToolCallError

    audit = InMemoryAuditEmitter()
    mcp, _ = _build(audit=audit)
    set_principal(GatewayPrincipal(org_id=ORG, permissions=(1 << 19), agent_id=AGENT))
    try:
        with pytest.raises(ToolCallError, match="invalid_params"):
            await mcp.call_tool("session.get", {"session_id": "not-a-uuid"})
    finally:
        set_principal(None)
    assert len(audit.events) == 1
    assert audit.events[0].success is False
    assert audit.events[0].error_code == "invalid_params"


@pytest.mark.asyncio
async def test_out_of_range_limit_reaches_gateway_typed_error() -> None:
    from app.errors import ToolCallError

    mcp, _ = _build()
    set_principal(GatewayPrincipal(org_id=ORG, permissions=(1 << 33), agent_id=AGENT))
    try:
        with pytest.raises(ToolCallError, match="invalid_params"):
            await mcp.call_tool("budget.get", {"limit": 500})
    finally:
        set_principal(None)
