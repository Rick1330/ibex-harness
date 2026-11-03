"""HTTP surface: probes, bearer challenge, MCP handshake, deny paths."""

from __future__ import annotations

from typing import Any

import pytest

from app.protocol import (
    MCP_PROTOCOL_VERSION_HEADER,
    PROTOCOL_VERSION_LATEST,
    PROTOCOL_VERSION_LEGACY,
    SUPPORTED_PROTOCOL_VERSIONS,
)
from tests.fixtures import (
    SESSION_ID,
    TOKEN_A,
    TOKEN_NO_SCOPE,
    AppOptions,
    StaticRateLimiter,
    disabled_settings,
    make_app,
    static_validator,
)


def _headers(token: str, protocol_version: str = PROTOCOL_VERSION_LATEST) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        MCP_PROTOCOL_VERSION_HEADER: protocol_version,
    }


def _initialize(protocol_version: str, request_id: int = 1) -> dict[str, Any]:
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


def _handshake(client: Any, token: str, protocol_version: str = PROTOCOL_VERSION_LATEST):
    headers = _headers(token, protocol_version)
    init = client.post("/mcp", headers=headers, json=_initialize(protocol_version))
    assert init.status_code in (200, 202), init.text
    client.post(
        "/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )
    return headers


def _call(client: Any, headers: dict[str, str], name: str, arguments: dict[str, Any]):
    return client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )


def test_mcp_requires_bearer() -> None:
    client, _ = make_app()
    with client:
        resp = client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )
    assert resp.status_code == 401
    assert "resource_metadata" in resp.headers["WWW-Authenticate"]


def test_mcp_invalid_token() -> None:
    client, _ = make_app()
    with client:
        resp = client.post(
            "/mcp",
            headers={"Authorization": "Bearer nope"},
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
    assert resp.status_code == 401


def test_auth_unavailable_fails_closed() -> None:
    client, _ = make_app(AppOptions(validator=static_validator(available=False)))
    with client:
        resp = client.post(
            "/mcp",
            headers={"Authorization": "Bearer x"},
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "auth_unavailable"


def test_ready_reports_unavailable_auth() -> None:
    client, _ = make_app(AppOptions(validator=static_validator(available=False)))
    with client:
        ready = client.get("/ready")
    assert ready.status_code == 503
    assert ready.json()["error"]["code"] == "service_not_ready"


@pytest.mark.parametrize(
    "protocol_version",
    sorted(SUPPORTED_PROTOCOL_VERSIONS),
    ids=sorted(SUPPORTED_PROTOCOL_VERSIONS),
)
def test_initialize_lists_operator_tools(protocol_version: str) -> None:
    assert protocol_version in (PROTOCOL_VERSION_LEGACY, PROTOCOL_VERSION_LATEST)
    client, _ = make_app()
    with client:
        headers = _handshake(client, TOKEN_A, protocol_version)
        listed = client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert listed.status_code in (200, 202), listed.text
        text = listed.text
    for name in ("session.get", "run.get", "evidence.query", "budget.get"):
        assert name in text


def test_tool_call_returns_redacted_metadata() -> None:
    client, _ = make_app()
    with client:
        headers = _handshake(client, TOKEN_A)
        called = _call(client, headers, "session.get", {"session_id": str(SESSION_ID)})
    assert called.status_code in (200, 202), called.text
    assert str(SESSION_ID) in called.text
    assert "secret_content" not in called.text


def test_tool_call_without_scope_is_error() -> None:
    client, sink = make_app()
    with client:
        headers = _handshake(client, TOKEN_NO_SCOPE)
        called = _call(client, headers, "session.get", {"session_id": str(SESSION_ID)})
        assert "permission_denied" in called.text
        assert '"isError":true' in called.text.replace(" ", "")
    assert any(event.error_code == "permission_denied" for event in sink.events)


def test_tool_call_rate_limited() -> None:
    client, sink = make_app(AppOptions(rate_limiter=StaticRateLimiter(allowed=False)))
    with client:
        headers = _handshake(client, TOKEN_A)
        called = _call(client, headers, "budget.get", {"active_only": True, "limit": 5})
        assert "rate_limited" in called.text
    assert any(event.error_code == "rate_limited" for event in sink.events)


def test_audit_records_successful_call() -> None:
    client, sink = make_app()
    with client:
        headers = _handshake(client, TOKEN_A)
        _call(client, headers, "evidence.query", {"limit": 5})
    assert any(event.success and event.tool_name == "evidence.query" for event in sink.events)


def test_disabled_gateway_has_no_mcp_surface() -> None:
    client, _ = make_app(AppOptions(settings=disabled_settings(), executor=None, validator=None))
    with client:
        assert client.post("/mcp", json={}).status_code == 404
        assert client.get("/health").status_code == 200


def test_malformed_session_id_is_typed_and_audited() -> None:
    client, sink = make_app()
    with client:
        headers = _handshake(client, TOKEN_A)
        called = _call(client, headers, "session.get", {"session_id": "not-a-uuid"})
    assert "invalid_params" in called.text
    assert '"isError":true' in called.text.replace(" ", "")
    assert any(event.error_code == "invalid_params" for event in sink.events)


def test_missing_required_argument_is_typed_and_audited() -> None:
    client, sink = make_app()
    with client:
        headers = _handshake(client, TOKEN_A)
        called = _call(client, headers, "session.get", {})
    assert "invalid_params" in called.text
    assert any(event.error_code == "invalid_params" for event in sink.events)


def test_extra_argument_is_typed_and_audited() -> None:
    client, sink = make_app()
    with client:
        headers = _handshake(client, TOKEN_A)
        called = _call(
            client,
            headers,
            "session.get",
            {"session_id": str(SESSION_ID), "org_id": "other-org"},
        )
    assert "invalid_params" in called.text
    assert any(event.error_code == "invalid_params" for event in sink.events)


def test_unknown_tool_is_typed_and_audited() -> None:
    client, sink = make_app()
    with client:
        headers = _handshake(client, TOKEN_A)
        called = _call(client, headers, "session.delete", {"session_id": str(SESSION_ID)})
    assert "tool_not_found" in called.text
    assert any(event.error_code == "tool_not_found" for event in sink.events)
