"""Config and transport gating tests."""

from __future__ import annotations

import pytest

from app.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_default_transport_http() -> None:
    s = Settings()
    assert s.transport == "streamable_http"
    s.validate_transport_policy()


def test_stdio_requires_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_MCP_TRANSPORT", "stdio")
    monkeypatch.setenv("IBEX_MCP_ALLOW_STDIO", "false")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="ALLOW_STDIO"):
        get_settings()


def test_stdio_forbidden_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_ENV", "production")
    monkeypatch.setenv("IBEX_MCP_TRANSPORT", "stdio")
    monkeypatch.setenv("IBEX_MCP_ALLOW_STDIO", "true")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="production"):
        get_settings()


def test_stdio_allowed_in_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_ENV", "development")
    monkeypatch.setenv("IBEX_MCP_TRANSPORT", "stdio")
    monkeypatch.setenv("IBEX_MCP_ALLOW_STDIO", "true")
    get_settings.cache_clear()
    s = get_settings()
    assert s.transport == "stdio"


def test_production_rejects_loopback_resource_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_ENV", "production")
    monkeypatch.setenv("IBEX_MCP_RESOURCE_URL", "http://127.0.0.1:8090/mcp")
    monkeypatch.setenv("IBEX_MCP_AUTH_SERVER_URL", "https://auth.example.com")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="https"):
        get_settings()


def test_production_rejects_loopback_auth_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_ENV", "production")
    monkeypatch.setenv("IBEX_MCP_RESOURCE_URL", "https://mcp.example.com/mcp")
    monkeypatch.setenv("IBEX_MCP_AUTH_SERVER_URL", "https://localhost:8080")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="loopback"):
        get_settings()


def test_production_accepts_public_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_ENV", "production")
    monkeypatch.setenv("IBEX_MCP_RESOURCE_URL", "https://mcp.example.com/mcp")
    monkeypatch.setenv("IBEX_MCP_AUTH_SERVER_URL", "https://auth.example.com")
    get_settings.cache_clear()
    s = get_settings()
    assert s.resource_url.startswith("https://")
    assert s.auth_server_url.startswith("https://")


def test_production_rejects_loopback_ipv4_range(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_ENV", "production")
    monkeypatch.setenv("IBEX_MCP_RESOURCE_URL", "https://127.0.0.2/mcp")
    monkeypatch.setenv("IBEX_MCP_AUTH_SERVER_URL", "https://auth.example.com")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="loopback"):
        get_settings()


def test_production_rejects_localhost_trailing_dot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_ENV", "production")
    monkeypatch.setenv("IBEX_MCP_RESOURCE_URL", "https://mcp.example.com/mcp")
    monkeypatch.setenv("IBEX_MCP_AUTH_SERVER_URL", "https://localhost./")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="loopback"):
        get_settings()
