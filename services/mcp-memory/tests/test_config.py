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
