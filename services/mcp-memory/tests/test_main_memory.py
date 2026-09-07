"""create_app memory-client wiring coverage."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.audit import MemoryAuditSink
from app.auth import StaticTokenValidator, ValidateResult
from app.config import Settings, get_settings
from app.main import create_app
from app.permissions import MEMORY_READ
from tests.memory_fixtures import AGENT, ORG, stub_memory_client


@pytest.fixture(autouse=True)
def _clear_settings() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _settings(**overrides: object) -> Settings:
    base = {
        "transport": "streamable_http",
        "resource_url": "http://testserver/mcp",
        "auth_server_url": "http://auth.test",
        "auth_grpc_addr": "127.0.0.1:1",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_create_app_warns_when_memory_url_unset(caplog: pytest.LogCaptureFixture) -> None:
    validator = StaticTokenValidator(
        {"t": ValidateResult(org_id=ORG, permissions=MEMORY_READ, agent_id=AGENT)}
    )
    with caplog.at_level(logging.WARNING):
        application = create_app(
            settings=_settings(memory_http_url=""),
            validator=validator,
            audit_sink=MemoryAuditSink(),
        )
    assert any("IBEX_MEMORY_HTTP_URL unset" in r.message for r in caplog.records)
    with TestClient(application) as client:
        assert client.get("/health").status_code == 200


def test_create_app_builds_owned_memory_client() -> None:
    validator = StaticTokenValidator(
        {"t": ValidateResult(org_id=ORG, permissions=MEMORY_READ, agent_id=AGENT)}
    )
    application = create_app(
        settings=_settings(
            memory_http_url="http://memory.internal",
            memory_timeout_ms=1500,
        ),
        validator=validator,
        audit_sink=MemoryAuditSink(),
    )
    with TestClient(application) as client:
        assert client.get("/health").status_code == 200
        mem = application.state.mcp.memory_client
        assert mem is not None
        assert mem.base_url == "http://memory.internal"
        assert mem.timeout_seconds == 1.5


def test_create_app_keeps_injected_client() -> None:
    injected = stub_memory_client()
    validator = StaticTokenValidator(
        {"t": ValidateResult(org_id=ORG, permissions=MEMORY_READ, agent_id=AGENT)}
    )
    application = create_app(
        settings=_settings(memory_http_url="http://ignored"),
        validator=validator,
        audit_sink=MemoryAuditSink(),
        memory_client=injected,
    )
    with TestClient(application) as client:
        assert client.get("/health").status_code == 200
        assert application.state.mcp.memory_client is injected
