"""HTTP probe, auth challenge, and MCP conformance handshake tests."""

from __future__ import annotations

import json
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from app.audit import MemoryAuditSink
from app.auth import StaticTokenValidator, ValidateResult
from app.config import Settings, get_settings
from app.main import CreateAppDeps, create_app
from app.permissions import MEMORY_READ, MEMORY_WRITE
from app.probes import build_protected_resource_metadata
from app.protocol import (
    MCP_PROTOCOL_VERSION_HEADER,
    PROTOCOL_VERSION_LATEST,
    PROTOCOL_VERSION_LEGACY,
    SUPPORTED_PROTOCOL_VERSIONS,
)
from tests.memory_fixtures import (
    CreatedMemory,
    create_memory_response,
    empty_search_response,
    memory_client_for,
    stub_memory_client,
)

ORG = UUID("11111111-1111-1111-1111-111111111111")
ORG_B = UUID("22222222-2222-2222-2222-222222222222")
AGENT = UUID("33333333-3333-3333-3333-333333333333")
TOKEN_A = "tok-org-a"
TOKEN_B = "tok-org-b"
TOKEN_READ_ONLY = "tok-read"


@pytest.fixture(autouse=True)
def _clear_settings() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _app(*, memory_client=None) -> tuple[TestClient, MemoryAuditSink]:
    settings = Settings(
        transport="streamable_http",
        resource_url="http://testserver/mcp",
        auth_server_url="http://auth.test",
        auth_grpc_addr="127.0.0.1:1",
    )
    validator = StaticTokenValidator(
        {
            TOKEN_A: ValidateResult(
                org_id=ORG, permissions=MEMORY_READ | MEMORY_WRITE, agent_id=AGENT
            ),
            TOKEN_B: ValidateResult(
                org_id=ORG_B, permissions=MEMORY_READ | MEMORY_WRITE, agent_id=AGENT
            ),
            TOKEN_READ_ONLY: ValidateResult(
                org_id=ORG, permissions=MEMORY_READ, agent_id=AGENT
            ),
        }
    )
    sink = MemoryAuditSink()
    application = create_app(
        settings=settings,
        deps=CreateAppDeps(
            validator=validator,
            audit_sink=sink,
            memory_client=memory_client
            or stub_memory_client(org_id=ORG, agent_id=AGENT),
        ),
    )
    return TestClient(application), sink


def _mcp_headers(token: str, protocol_version: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        MCP_PROTOCOL_VERSION_HEADER: protocol_version,
    }


def _initialize_payload(protocol_version: str, request_id: int = 1) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "initialize",
        "params": {
            "protocolVersion": protocol_version,
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        },
    }


def _parse_jsonrpc_result(resp: object) -> dict[str, object]:
    body = resp.json()
    assert "result" in body, body
    assert isinstance(body["result"], dict)
    return body["result"]


def test_health_and_ready() -> None:
    client, _ = _app()
    with client:
        assert client.get("/health").status_code == 200
        ready = client.get("/ready")
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"


def test_protected_resource_metadata() -> None:
    """RFC 9728 minimum discovery fields for the MCP resource server."""
    client, _ = _app()
    with client:
        resp = client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200
    body = resp.json()
    # Minimum fields locked for 3.5.E.1 (deviation: exhaustive RFC 9728 later).
    assert body["resource"] == "http://testserver/mcp"
    assert body["authorization_servers"] == ["http://auth.test"]
    assert body["scopes_supported"] == ["memory:read", "memory:write"]
    assert set(body.keys()) >= {
        "resource",
        "authorization_servers",
        "scopes_supported",
    }


def test_build_protected_resource_metadata_helper() -> None:
    settings = Settings(
        resource_url="https://mcp.example.com/mcp",
        auth_server_url="https://auth.example.com",
    )
    meta = build_protected_resource_metadata(settings)
    assert meta["resource"] == "https://mcp.example.com/mcp"
    assert meta["authorization_servers"] == ["https://auth.example.com"]
    assert meta["scopes_supported"] == ["memory:read", "memory:write"]


def test_mcp_requires_bearer() -> None:
    client, _ = _app()
    with client:
        resp = client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )
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
    application = create_app(
        settings=settings,
        deps=CreateAppDeps(validator=validator, audit_sink=MemoryAuditSink()),
    )
    with TestClient(application) as client:
        resp = client.post(
            "/mcp",
            headers={"Authorization": "Bearer x"},
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "auth_unavailable"


@pytest.mark.parametrize(
    "protocol_version",
    sorted(SUPPORTED_PROTOCOL_VERSIONS),
    ids=sorted(SUPPORTED_PROTOCOL_VERSIONS),
)
def test_mcp_initialize_negotiates_protocol_version(protocol_version: str) -> None:
    """Both legacy and LATEST protocol versions must negotiate to the requested value."""
    assert protocol_version in (PROTOCOL_VERSION_LEGACY, PROTOCOL_VERSION_LATEST)
    client, _sink = _app()
    headers = _mcp_headers(TOKEN_A, protocol_version)
    with client:
        init = client.post("/mcp", headers=headers, json=_initialize_payload(protocol_version))
        assert init.status_code in (200, 202), init.text
        result = _parse_jsonrpc_result(init)
        assert result["protocolVersion"] == protocol_version
        # Required after initialize for Streamable HTTP clients.
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
        listed_text = listed.text
        assert "search_memory" in listed_text
        assert "write_memory" in listed_text
        assert "record_feedback" in listed_text
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
        assert "results" in called.text or "search_memory" in called.text
        assert "isError" not in called.text or '"isError":false' in called.text.replace(" ", "")


def test_mcp_initialize_and_tools_list() -> None:
    """Back-compat alias: default conformance path uses LATEST protocol version."""
    test_mcp_initialize_negotiates_protocol_version(PROTOCOL_VERSION_LATEST)


def _capturing_org_b_memory() -> tuple[object, list[httpx.Request]]:
    outbound: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        outbound.append(request)
        if request.url.path.endswith("/search"):
            return empty_search_response()
        return create_memory_response(CreatedMemory(org_id=ORG_B, agent_id=AGENT))

    return memory_client_for(handler), outbound


def _mcp_session(client: TestClient, token: str) -> dict[str, str]:
    headers = _mcp_headers(token, PROTOCOL_VERSION_LATEST)
    init = client.post(
        "/mcp", headers=headers, json=_initialize_payload(PROTOCOL_VERSION_LATEST)
    )
    assert init.status_code in (200, 202), init.text
    client.post(
        "/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )
    return headers


def _tools_call(client: TestClient, call: dict[str, object]) -> object:
    """call keys: headers, request_id, name, arguments."""
    return client.post(
        "/mcp",
        headers=call["headers"],  # type: ignore[arg-type]
        json={
            "jsonrpc": "2.0",
            "id": call["request_id"],
            "method": "tools/call",
            "params": {"name": call["name"], "arguments": call["arguments"]},
        },
    )


def _assert_tool_ok(resp: object) -> None:
    assert resp.status_code in (200, 202), resp.text
    compact = resp.text.replace(" ", "")
    assert "isError" not in resp.text or '"isError":false' in compact


def _assert_tool_error(resp: object) -> None:
    assert resp.status_code in (200, 202), resp.text
    assert "isError" in resp.text or "permission" in resp.text.lower()


def _assert_org_b_outbound(outbound: list[httpx.Request], *, expected_calls: int) -> None:
    assert len(outbound) == expected_calls
    for req in outbound:
        assert req.headers["Authorization"] == f"Bearer {TOKEN_B}"
        assert TOKEN_A not in req.headers.get("Authorization", "")
        if req.content:
            assert "org_id" not in json.loads(req.content)


def test_tools_call_org_b_forwards_bearer_never_org_id() -> None:
    """ISO-MCP-01: Org B tools/call must forward Org B bearer; never client org_id."""
    mem, outbound = _capturing_org_b_memory()
    client, _sink = _app(memory_client=mem)
    with client:
        headers = _mcp_session(client, TOKEN_B)
        _assert_tool_ok(
            _tools_call(
                client,
                {
                    "headers": headers,
                    "request_id": 2,
                    "name": "search_memory",
                    "arguments": {"query": "tenant"},
                },
            )
        )
        _assert_tool_ok(
            _tools_call(
                client,
                {
                    "headers": headers,
                    "request_id": 3,
                    "name": "write_memory",
                    "arguments": {"content": "org-b note"},
                },
            )
        )
    _assert_org_b_outbound(outbound, expected_calls=2)


def test_tools_call_rejects_client_org_override_and_agent_mismatch() -> None:
    """Client org_id / foreign agent_id must not reach memory HTTP."""
    mem, outbound = _capturing_org_b_memory()
    client, _sink = _app(memory_client=mem)
    with client:
        headers = _mcp_session(client, TOKEN_B)
        _assert_tool_error(
            _tools_call(
                client,
                {
                    "headers": headers,
                    "request_id": 4,
                    "name": "search_memory",
                    "arguments": {"query": "x", "org_id": str(ORG)},
                },
            )
        )
        _assert_tool_error(
            _tools_call(
                client,
                {
                    "headers": headers,
                    "request_id": 5,
                    "name": "write_memory",
                    "arguments": {"content": "x", "agent_id": str(ORG)},
                },
            )
        )
    assert outbound == []


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


def test_supported_protocol_versions_constant() -> None:
    assert PROTOCOL_VERSION_LEGACY == "2024-11-05"
    assert PROTOCOL_VERSION_LATEST == "2025-11-25"
    assert SUPPORTED_PROTOCOL_VERSIONS == frozenset(
        {PROTOCOL_VERSION_LEGACY, PROTOCOL_VERSION_LATEST}
    )
