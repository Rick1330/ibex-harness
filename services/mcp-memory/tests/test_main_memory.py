"""create_app memory-client wiring coverage."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.agent_verifier import AllowAllAgentVerifier
from app.audit import MemoryAuditSink
from app.auth import StaticTokenValidator, ValidateResult
from app.auth_breaker import BreakingTokenValidator
from app.config import Settings, get_settings
from app.main import CreateAppDeps, create_app
from app.permissions import MEMORY_READ
from app.ratelimit import RedisMcpLimiter
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
            deps=CreateAppDeps(validator=validator, audit_sink=MemoryAuditSink(), agent_verifier=AllowAllAgentVerifier()),
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
        deps=CreateAppDeps(validator=validator, audit_sink=MemoryAuditSink(), agent_verifier=AllowAllAgentVerifier()),
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
        deps=CreateAppDeps(
            validator=validator,
            audit_sink=MemoryAuditSink(),
            memory_client=injected,
            agent_verifier=AllowAllAgentVerifier(),
        ),
    )
    with TestClient(application) as client:
        assert client.get("/health").status_code == 200
        assert application.state.mcp.memory_client is injected


def test_create_app_keeps_injected_breaker() -> None:
    inner = StaticTokenValidator(
        {"t": ValidateResult(org_id=ORG, permissions=MEMORY_READ, agent_id=AGENT)}
    )
    breaker = BreakingTokenValidator(inner, failure_threshold=2, cooldown_seconds=1.0)
    application = create_app(
        settings=_settings(),
        deps=CreateAppDeps(validator=breaker, audit_sink=MemoryAuditSink(), agent_verifier=AllowAllAgentVerifier()),
    )
    with TestClient(application) as client:
        assert client.get("/health").status_code == 200
        assert application.state.mcp.validator is breaker


def test_create_app_closes_owned_redis_limiter() -> None:
    validator = StaticTokenValidator(
        {"t": ValidateResult(org_id=ORG, permissions=MEMORY_READ, agent_id=AGENT)}
    )
    application = create_app(
        settings=_settings(redis_url="redis://127.0.0.1:9/0"),
        deps=CreateAppDeps(validator=validator, audit_sink=MemoryAuditSink(), agent_verifier=AllowAllAgentVerifier()),
    )
    with TestClient(application) as client:
        assert client.get("/health").status_code == 200
        assert isinstance(application.state.mcp.rate_limiter, RedisMcpLimiter)
    # Lifespan exit path closes owned RedisMcpLimiter (no exception).
