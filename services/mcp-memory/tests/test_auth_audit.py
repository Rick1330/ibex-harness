"""Auth middleware emits mcp_tool_calls audit rows on 401/503."""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.agent_verifier import AllowAllAgentVerifier
from app.audit import MemoryAuditSink
from app.auth import StaticTokenValidator, ValidateResult
from app.config import Settings, get_settings
from app.main import CreateAppDeps, create_app
from app.middleware import AUTH_AUDIT_ORG_UNKNOWN
from app.permissions import MEMORY_READ
from tests.memory_fixtures import AGENT, ORG


@pytest.fixture(autouse=True)
def _clear_settings() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_auth_401_emits_audit() -> None:
    settings = Settings(
        transport="streamable_http",
        resource_url="http://testserver/mcp",
        auth_server_url="http://auth.test",
        auth_grpc_addr="127.0.0.1:1",
    )
    sink = MemoryAuditSink()
    application = create_app(
        settings=settings,
        deps=CreateAppDeps(validator=StaticTokenValidator({}), audit_sink=sink, agent_verifier=AllowAllAgentVerifier()),
    )
    with TestClient(application) as client:
        resp = client.post(
            "/mcp",
            headers={"Authorization": "Bearer bad", "Accept": "application/json"},
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
    assert resp.status_code == 401
    assert any(
        e.tool_name == "auth" and e.error_code == "unauthorized" and e.success is False
        for e in sink.events
    )
    auth_events = [e for e in sink.events if e.tool_name == "auth"]
    assert auth_events[0].org_id == AUTH_AUDIT_ORG_UNKNOWN


def test_auth_503_emits_audit() -> None:
    settings = Settings(
        transport="streamable_http",
        resource_url="http://testserver/mcp",
        auth_server_url="http://auth.test",
        auth_grpc_addr="127.0.0.1:1",
    )
    sink = MemoryAuditSink()
    validator = StaticTokenValidator(
        {
            "tok": ValidateResult(
                org_id=ORG, permissions=MEMORY_READ, agent_id=AGENT
            )
        },
        available=False,
    )
    application = create_app(
        settings=settings,
        deps=CreateAppDeps(validator=validator, audit_sink=sink, agent_verifier=AllowAllAgentVerifier()),
    )
    with TestClient(application) as client:
        # Trip breaker (N=5) then still 503
        for _ in range(6):
            resp = client.post(
                "/mcp",
                headers={"Authorization": "Bearer tok", "Accept": "application/json"},
                json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            )
            assert resp.status_code == 503
    assert any(
        e.tool_name == "auth" and e.error_code == "auth_unavailable"
        for e in sink.events
    )


def test_config_rejects_bad_overrides() -> None:
    with pytest.raises(ValueError, match="invalid"):
        Settings(
            transport="streamable_http",
            resource_url="http://testserver/mcp",
            auth_server_url="http://auth.test",
            rate_limit_org_overrides="not-uuid=10",
        )


def test_settings_rate_limit_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    # REDIS_URL is a shared alias; CI runners may export it — pin empty for default assert.
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("IBEX_MCP_REDIS_URL", raising=False)
    settings = Settings(
        transport="streamable_http",
        resource_url="http://testserver/mcp",
        auth_server_url="http://auth.test",
        redis_url="",
    )
    assert settings.rate_limit_rpm == 120
    assert settings.redis_url == ""
    org = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    settings2 = Settings(
        transport="streamable_http",
        resource_url="http://testserver/mcp",
        auth_server_url="http://auth.test",
        rate_limit_org_overrides=f"{org}=50",
    )
    assert settings2.rate_limit_org_override_map == {org: 50}
