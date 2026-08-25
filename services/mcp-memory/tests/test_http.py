"""HTTP probe, auth challenge, and MCP conformance-ish handshake tests."""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.audit import MemoryAuditSink
from app.auth import StaticTokenValidator, ValidateResult
from app.config import Settings, get_settings
from app.main import create_app
from app.permissions import MEMORY_READ, MEMORY_WRITE

ORG = UUID("11111111-1111-1111-1111-111111111111")
ORG_B = UUID("22222222-2222-2222-2222-222222222222")
TOKEN_A = "tok-org-a"
TOKEN_B = "tok-org-b"
TOKEN_READ_ONLY = "tok-read"


@pytest.fixture(autouse=True)
def _clear_settings() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _app() -> TestClient:
    settings = Settings(
        transport="streamable_http",
        resource_url="http://testserver/mcp",
        auth_server_url="http://auth.test",
        auth_grpc_addr="127.0.0.1:1",
    )
    validator = StaticTokenValidator(
        {
            TOKEN_A: ValidateResult(org_id=ORG, permissions=MEMORY_READ | MEMORY_WRITE),
            TOKEN_B: ValidateResult(org_id=ORG_B, permissions=MEMORY_READ | MEMORY_WRITE),
            TOKEN_READ_ONLY: ValidateResult(org_id=ORG, permissions=MEMORY_READ),
        }
    )
    sink = MemoryAuditSink()
    application = create_app(settings=settings, validator=validator, audit_sink=sink)
    return TestClient(application), sink


def test_health_and_ready() -> None:
    client, _ = _app()
    with client:
        assert client.get("/health").status_code == 200
        ready = client.get("/ready")
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"


def test_protected_resource_metadata() -> None:
    client, _ = _app()
    with client:
        resp = client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200
    body = resp.json()
    assert body["resource"] == "http://testserver/mcp"
    assert body["authorization_servers"] == ["http://auth.test"]


def test_mcp_requires_bearer() -> None:
    client, _ = _app()
    with client:
        resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert resp.status_code == 401
    assert "WWW-Authenticate" in resp.headers
    assert "resource_metadata" in resp.headers["WWW-Authenticate"]


def test_mcp_invalid_token() -> None:
    client, _ = _app()
    with client:
        resp = client.post(
            "/mcp",
            headers={"Authorization": "Bearer nope"},
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
    assert resp.status_code == 401


def test_auth_unavailable_fail_closed() -> None:
    settings = Settings(resource_url="http://testserver/mcp")
    validator = StaticTokenValidator({}, available=False)
    application = create_app(settings=settings, validator=validator, audit_sink=MemoryAuditSink())
    with TestClient(application) as client:
        resp = client.post(
            "/mcp",
            headers={"Authorization": "Bearer x"},
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "auth_unavailable"


def test_mcp_initialize_and_tools_list() -> None:
    client, _sink = _app()
    headers = {
        "Authorization": f"Bearer {TOKEN_A}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    with client:
        init = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            },
        )
        assert init.status_code in (200, 202), init.text
        # Required after initialize for many MCP servers.
        client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        listed = client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert listed.status_code in (200, 202), listed.text
        text = listed.text
        assert "search_memory" in text
        assert "write_memory" in text
        called = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "search_memory", "arguments": {"query": "q1"}},
            },
        )
        assert called.status_code in (200, 202), called.text
        assert "stub" in called.text or "search_memory" in called.text or "mcp_stub" in called.text


def test_metrics_endpoint() -> None:
    client, _ = _app()
    with client:
        resp = client.get("/metrics")
    assert resp.status_code == 200
    assert b"python_info" in resp.content or b"ibex_mcp" in resp.content


def test_authorization_token_not_echoed() -> None:
    client, _ = _app()
    secret = "super-secret-token-value"
    with client:
        resp = client.post(
            "/mcp",
            headers={"Authorization": f"Bearer {secret}"},
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
    assert secret not in resp.text
