"""Fixtures for ISO-MCP-01..03 against live auth + memory HTTP."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.audit import MemoryAuditSink
from app.config import Settings, get_settings
from app.main import CreateAppDeps, create_app
from app.protocol import MCP_PROTOCOL_VERSION_HEADER, PROTOCOL_VERSION_LATEST


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.skip(f"{name} required for iso_mcp tests")
    return value


@pytest.fixture(scope="module")
def iso_env() -> dict[str, str]:
    return {
        "auth_grpc": _require_env("IBEX_AUTH_GRPC_ADDR"),
        "memory_http": _require_env("IBEX_MEMORY_HTTP_URL"),
        "token_a": _require_env("IBEX_ISO_MCP_TOKEN_A"),
        "token_org": _require_env("IBEX_ISO_MCP_TOKEN_ORG_SCOPED"),
        "token_suspended": _require_env("IBEX_ISO_MCP_TOKEN_SUSPENDED"),
        "org_a": _require_env("IBEX_ISO_MCP_ORG_A"),
        "org_b": _require_env("IBEX_ISO_MCP_ORG_B"),
        "agent_b": _require_env("IBEX_ISO_MCP_AGENT_B"),
        "agent_user_b": _require_env("IBEX_ISO_MCP_AGENT_USER_B"),
        "agent_suspended": _require_env("IBEX_ISO_MCP_AGENT_SUSPENDED"),
    }


@pytest.fixture
def iso_ids(iso_env: dict[str, str]) -> dict[str, UUID]:
    return {
        "org_a": UUID(iso_env["org_a"]),
        "org_b": UUID(iso_env["org_b"]),
        "agent_b": UUID(iso_env["agent_b"]),
        "agent_user_b": UUID(iso_env["agent_user_b"]),
        "agent_suspended": UUID(iso_env["agent_suspended"]),
    }


@pytest.fixture
def iso_app(iso_env: dict[str, str]) -> Iterator[tuple[TestClient, MemoryAuditSink]]:
    get_settings.cache_clear()
    sink = MemoryAuditSink()
    settings = Settings(
        transport="streamable_http",
        resource_url="http://testserver/mcp",
        auth_server_url="http://auth.test",
        auth_grpc_addr=iso_env["auth_grpc"],
        auth_timeout_ms=2000,
        memory_http_url=iso_env["memory_http"],
        memory_timeout_ms=10_000,
        redis_url="",
    )
    application = create_app(
        settings=settings,
        deps=CreateAppDeps(audit_sink=sink),
    )
    client = TestClient(application)
    with client:
        yield client, sink
    get_settings.cache_clear()


def mcp_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        MCP_PROTOCOL_VERSION_HEADER: PROTOCOL_VERSION_LATEST,
    }


def initialize_payload() -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL_VERSION_LATEST,
            "capabilities": {},
            "clientInfo": {"name": "iso-mcp", "version": "0"},
        },
    }


def mcp_session(client: TestClient, token: str) -> dict[str, str]:
    headers = mcp_headers(token)
    init = client.post("/mcp", headers=headers, json=initialize_payload())
    assert init.status_code in (200, 202), init.text
    client.post(
        "/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )
    return headers


@dataclass(frozen=True, slots=True)
class ToolCallSpec:
    headers: dict[str, str]
    request_id: int
    name: str
    arguments: dict[str, object]


def tools_call(client: TestClient, call: ToolCallSpec) -> object:
    return client.post(
        "/mcp",
        headers=call.headers,
        json={
            "jsonrpc": "2.0",
            "id": call.request_id,
            "method": "tools/call",
            "params": {"name": call.name, "arguments": call.arguments},
        },
    )


def assert_permission_denied(
    resp: object,
    *,
    sink: MemoryAuditSink,
    tool_name: str,
    events_before: int,
) -> None:
    assert resp.status_code in (200, 202), resp.text
    body = resp.json()
    result = body.get("result")
    assert isinstance(result, dict), body
    assert result.get("isError") is True, body
    blob = resp.text.lower()
    assert "not_found" not in blob
    new_events = sink.events[events_before:]
    assert any(
        e.tool_name == tool_name
        and e.success is False
        and e.error_code == "permission_denied"
        for e in new_events
    ), new_events


def assert_tool_ok(resp: object) -> None:
    assert resp.status_code in (200, 202), resp.text
    body = resp.json()
    result = body.get("result")
    assert isinstance(result, dict), body
    assert result.get("isError") is not True, body
