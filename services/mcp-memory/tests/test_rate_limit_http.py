"""HTTP tools/call rate limit → CallToolResult isError (not HTTP 429)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent_verifier import AllowAllAgentVerifier
from app.audit import MemoryAuditSink
from app.auth import StaticTokenValidator, ValidateResult
from app.config import Settings, get_settings
from app.main import CreateAppDeps, create_app
from app.permissions import MEMORY_READ, MEMORY_WRITE
from app.protocol import MCP_PROTOCOL_VERSION_HEADER, PROTOCOL_VERSION_LATEST
from app.ratelimit import McpRateLimiter, RateLimitResult
from tests.memory_fixtures import AGENT, ORG, stub_memory_client

TOKEN = "tok-rl"


@dataclass
class _DenyAfter(McpRateLimiter):
    remaining_allows: int

    async def check(self, org_id: UUID) -> RateLimitResult:
        del org_id
        if self.remaining_allows > 0:
            self.remaining_allows -= 1
            return RateLimitResult(True, 1, 0, 0)
        return RateLimitResult(False, 1, 0, 0)


@pytest.fixture(autouse=True)
def _clear_settings() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _rate_limit_app(sink: MemoryAuditSink) -> FastAPI:
    settings = Settings(
        transport="streamable_http",
        resource_url="http://testserver/mcp",
        auth_server_url="http://auth.test",
        auth_grpc_addr="127.0.0.1:1",
        redis_url="",
    )
    return create_app(
        settings=settings,
        deps=CreateAppDeps(
            validator=StaticTokenValidator(
                {
                    TOKEN: ValidateResult(
                        org_id=ORG,
                        permissions=MEMORY_READ | MEMORY_WRITE,
                        agent_id=AGENT,
                    )
                }
            ),
            audit_sink=sink,
            memory_client=stub_memory_client(org_id=ORG, agent_id=AGENT),
            rate_limiter=_DenyAfter(remaining_allows=0),
            agent_verifier=AllowAllAgentVerifier(),
        ),
    )


def _mcp_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        MCP_PROTOCOL_VERSION_HEADER: PROTOCOL_VERSION_LATEST,
    }


def _initialize_session(client: TestClient, headers: dict[str, str]) -> None:
    init = client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION_LATEST,
                "capabilities": {},
                "clientInfo": {"name": "t", "version": "0"},
            },
        },
    )
    assert init.status_code in (200, 202)
    client.post(
        "/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )


def test_tools_call_rate_limited_is_error_not_http_429() -> None:
    sink = MemoryAuditSink()
    headers = _mcp_headers()
    with TestClient(_rate_limit_app(sink)) as client:
        _initialize_session(client, headers)
        resp = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "search_memory",
                    "arguments": {"query": "burst"},
                },
            },
        )
    assert resp.status_code != 429
    assert resp.status_code in (200, 202), resp.text
    body = json.loads(resp.text)
    assert body["result"]["isError"] is True
    assert any(e.error_code == "rate_limited" for e in sink.events)
