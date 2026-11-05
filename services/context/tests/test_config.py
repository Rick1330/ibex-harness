"""Settings tests for the ADR-0096 secret fields."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from app.config import ContextSettings

TOKEN = "context-test-service-token-0123456789abcdef"
_ALIASES = (
    "IBEX_CONTEXT_GRPC_SERVICE_TOKEN",
    "IBEX_CONTEXT_MEMORY_API_TOKEN",
    "MEMORY_API_TOKEN",
)


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ALIASES:
        monkeypatch.delenv(name, raising=False)


def test_grpc_service_token_reads_the_explicit_env_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("IBEX_CONTEXT_GRPC_SERVICE_TOKEN", TOKEN)
    settings = ContextSettings()
    assert isinstance(settings.grpc_service_token, SecretStr)
    assert settings.grpc_service_token.get_secret_value() == TOKEN
    assert TOKEN not in repr(settings)


def test_memory_api_token_is_a_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("IBEX_CONTEXT_MEMORY_API_TOKEN", "memory-token")
    settings = ContextSettings()
    assert isinstance(settings.memory_api_token, SecretStr)
    assert settings.memory_api_token.get_secret_value() == "memory-token"
    assert "memory-token" not in repr(settings)


def test_memory_api_token_falls_back_to_the_legacy_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("MEMORY_API_TOKEN", "legacy-token")
    assert ContextSettings().memory_api_token.get_secret_value() == "legacy-token"


def test_secret_tokens_default_to_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    settings = ContextSettings()
    assert settings.grpc_service_token.get_secret_value() == ""
    assert settings.memory_api_token.get_secret_value() == ""


def test_grpc_addr_defaults_to_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IBEX_CONTEXT_GRPC_ADDR", raising=False)
    assert ContextSettings().grpc_addr == "127.0.0.1:9092"
