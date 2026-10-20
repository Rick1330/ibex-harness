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


def _validator() -> StaticTokenValidator:
    return StaticTokenValidator(
        {"t": ValidateResult(org_id=ORG, permissions=MEMORY_READ, agent_id=AGENT)}
    )


def _deps(**overrides: object) -> CreateAppDeps:
    values: dict[str, object] = {
        "validator": _validator(),
        "audit_sink": MemoryAuditSink(),
        "agent_verifier": AllowAllAgentVerifier(),
    }
    values.update(overrides)
    return CreateAppDeps(**values)  # type: ignore[arg-type]


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
    with caplog.at_level(logging.WARNING):
        application = create_app(
            settings=_settings(memory_http_url=""),
            deps=_deps(),
        )
    assert any("IBEX_MEMORY_HTTP_URL unset" in r.message for r in caplog.records)
    with TestClient(application) as client:
        assert client.get("/health").status_code == 200


def test_create_app_builds_owned_memory_client() -> None:
    application = create_app(
        settings=_settings(
            memory_http_url="http://memory.internal",
            memory_timeout_ms=1500,
        ),
        deps=_deps(),
    )
    with TestClient(application) as client:
        assert client.get("/health").status_code == 200
        mem = application.state.mcp.memory_client
        assert mem is not None
        assert mem.base_url == "http://memory.internal"
        assert mem.timeout_seconds == 1.5


def test_create_app_keeps_injected_client() -> None:
    injected = stub_memory_client()
    application = create_app(
        settings=_settings(memory_http_url="http://ignored"),
        deps=_deps(memory_client=injected),
    )
    with TestClient(application) as client:
        assert client.get("/health").status_code == 200
        assert application.state.mcp.memory_client is injected


def test_create_app_keeps_injected_breaker() -> None:
    breaker = BreakingTokenValidator(_validator(), failure_threshold=2, cooldown_seconds=1.0)
    application = create_app(
        settings=_settings(),
        deps=_deps(validator=breaker),
    )
    with TestClient(application) as client:
        assert client.get("/health").status_code == 200
        assert application.state.mcp.validator is breaker


def test_create_app_builds_owned_agent_verifier() -> None:
    from app.agent_verifier import GRPCAgentVerifier
    from app.main import _resolve_agent_verifier

    verifier, owned = _resolve_agent_verifier(
        _settings(auth_grpc_addr="127.0.0.1:9", auth_timeout_ms=50),
        None,
    )
    assert owned is True
    assert isinstance(verifier, GRPCAgentVerifier)

    injected = AllowAllAgentVerifier()
    kept, owned_kept = _resolve_agent_verifier(_settings(), injected)
    assert kept is injected
    assert owned_kept is False


def test_create_app_closes_owned_redis_limiter() -> None:
    application = create_app(
        settings=_settings(redis_url="redis://127.0.0.1:9/0"),
        deps=_deps(),
    )
    with TestClient(application) as client:
        assert client.get("/health").status_code == 200
        assert isinstance(application.state.mcp.rate_limiter, RedisMcpLimiter)
    # Lifespan exit path closes owned RedisMcpLimiter (no exception).
