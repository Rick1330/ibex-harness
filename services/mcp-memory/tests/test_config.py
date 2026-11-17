"""Config and transport gating tests."""

from __future__ import annotations

import logging

import pytest

from app.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    # A protected profile requires the AuthService client CA (ADR-0097 §4).
    # Provide it by default so unrelated assertions reach their own checks;
    # the CA-specific test deletes it explicitly.
    monkeypatch.setenv("IBEX_AUTH_GRPC_CA_FILE", "/etc/ibex/auth-grpc-ca.pem")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class _CaptureHandler(logging.Handler):
    """Collect records on the logger itself, without relying on propagation."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _warn_records(settings: Settings) -> list[logging.LogRecord]:
    """Run warn_if_env_defaulted with a handler on app.config, propagation off.

    ``configure_logging`` sets ``app.propagate = False``. ``caplog`` attaches its
    handler to the root logger, so these assertions would silently depend on
    whether another test had reconfigured logging first. The handler sits on the
    logger the code is given, and propagation is forced off for the call, so the
    result is the same in any test order.
    """
    log = logging.getLogger("app.config")
    handler = _CaptureHandler()
    previous_propagate = log.propagate
    log.addHandler(handler)
    log.propagate = False
    try:
        settings.warn_if_env_defaulted(log)
    finally:
        log.removeHandler(handler)
        log.propagate = previous_propagate
    return handler.records


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
    monkeypatch.setenv("IBEX_MCP_REDIS_URL", "redis://redis.example.com:6379/0")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="loopback"):
        get_settings()


def test_production_accepts_public_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_ENV", "production")
    monkeypatch.setenv("IBEX_MCP_RESOURCE_URL", "https://mcp.example.com/mcp")
    monkeypatch.setenv("IBEX_MCP_AUTH_SERVER_URL", "https://auth.example.com")
    monkeypatch.setenv("IBEX_MCP_REDIS_URL", "redis://redis.example.com:6379/0")
    get_settings.cache_clear()
    s = get_settings()
    assert s.resource_url.startswith("https://")
    assert s.auth_server_url.startswith("https://")
    assert s.memory_http_url == ""


def test_production_allows_empty_memory_http_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_ENV", "production")
    monkeypatch.setenv("IBEX_MCP_RESOURCE_URL", "https://mcp.example.com/mcp")
    monkeypatch.setenv("IBEX_MCP_AUTH_SERVER_URL", "https://auth.example.com")
    monkeypatch.setenv("IBEX_MCP_REDIS_URL", "redis://redis.example.com:6379/0")
    monkeypatch.setenv("IBEX_MEMORY_HTTP_URL", "")
    get_settings.cache_clear()
    assert get_settings().memory_http_url == ""


def test_production_rejects_insecure_memory_http_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_ENV", "production")
    monkeypatch.setenv("IBEX_MCP_RESOURCE_URL", "https://mcp.example.com/mcp")
    monkeypatch.setenv("IBEX_MCP_AUTH_SERVER_URL", "https://auth.example.com")
    monkeypatch.setenv("IBEX_MCP_REDIS_URL", "redis://redis.example.com:6379/0")
    monkeypatch.setenv("IBEX_MEMORY_HTTP_URL", "http://memory.example.com")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="IBEX_MEMORY_HTTP_URL"):
        get_settings()


def test_production_rejects_loopback_memory_http_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_ENV", "production")
    monkeypatch.setenv("IBEX_MCP_RESOURCE_URL", "https://mcp.example.com/mcp")
    monkeypatch.setenv("IBEX_MCP_AUTH_SERVER_URL", "https://auth.example.com")
    monkeypatch.setenv("IBEX_MCP_REDIS_URL", "redis://redis.example.com:6379/0")
    monkeypatch.setenv("IBEX_MEMORY_HTTP_URL", "https://127.0.0.1:8080")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="loopback"):
        get_settings()


def test_production_accepts_public_memory_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_ENV", "production")
    monkeypatch.setenv("IBEX_MCP_RESOURCE_URL", "https://mcp.example.com/mcp")
    monkeypatch.setenv("IBEX_MCP_AUTH_SERVER_URL", "https://auth.example.com")
    monkeypatch.setenv("IBEX_MCP_REDIS_URL", "redis://redis.example.com:6379/0")
    monkeypatch.setenv("IBEX_MEMORY_HTTP_URL", "https://memory.example.com")
    get_settings.cache_clear()
    assert get_settings().memory_http_url == "https://memory.example.com"


def test_protected_profile_requires_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_ENV", "staging")
    monkeypatch.setenv("IBEX_MCP_REDIS_URL", "")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="REDIS_URL"):
        get_settings()


def test_production_rejects_loopback_ipv4_range(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_ENV", "production")
    monkeypatch.setenv("IBEX_MCP_RESOURCE_URL", "https://127.0.0.2/mcp")
    monkeypatch.setenv("IBEX_MCP_AUTH_SERVER_URL", "https://auth.example.com")
    monkeypatch.setenv("IBEX_MCP_REDIS_URL", "redis://redis.example.com:6379/0")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="loopback"):
        get_settings()


def test_production_rejects_localhost_trailing_dot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_ENV", "production")
    monkeypatch.setenv("IBEX_MCP_RESOURCE_URL", "https://mcp.example.com/mcp")
    monkeypatch.setenv("IBEX_MCP_AUTH_SERVER_URL", "https://localhost./")
    monkeypatch.setenv("IBEX_MCP_REDIS_URL", "redis://redis.example.com:6379/0")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="loopback"):
        get_settings()


def test_protected_profile_requires_auth_ca(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IBEX_AUTH_GRPC_CA_FILE", raising=False)
    with pytest.raises(ValueError, match="IBEX_AUTH_GRPC_CA_FILE"):
        Settings(env="staging", redis_url="redis://redis:6379/0")
    with pytest.raises(ValueError, match="IBEX_AUTH_GRPC_CA_FILE"):
        Settings(env="staging", redis_url="redis://redis:6379/0", auth_grpc_ca_file="   ")
    Settings(env="development")
    Settings(
        env="staging",
        redis_url="redis://redis:6379/0",
        auth_grpc_ca_file="/etc/ibex/auth-grpc-ca.pem",
    )


def test_unset_env_warns_about_the_relaxed_posture(monkeypatch: pytest.MonkeyPatch) -> None:
    # P1-14/S11: an unset IBEX_ENV silently selects development. The default
    # stays, but the relaxation has to be visible in the first log lines.
    monkeypatch.delenv("IBEX_ENV", raising=False)
    monkeypatch.delenv("IBEX_MCP_ENV", raising=False)
    settings = Settings()
    assert settings.env == "development"
    assert settings.env_was_explicit is False
    records = _warn_records(settings)
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    message = records[0].getMessage()
    assert "IBEX_ENV is not set" in message
    assert "DNS-rebinding" in message


def test_explicit_env_does_not_warn() -> None:
    settings = Settings(env="development")
    assert settings.env_was_explicit is True
    assert _warn_records(settings) == []


@pytest.mark.parametrize("raw", ["", " ", "\t\n "])
def test_blank_env_is_treated_as_unset(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    # A blank IBEX_ENV counted as explicit: it was coerced to development and
    # suppressed the relaxed-posture warning, so the operator saw a
    # protected-looking setting that did nothing.
    monkeypatch.delenv("IBEX_ENV", raising=False)
    monkeypatch.delenv("IBEX_MCP_ENV", raising=False)
    supplied = Settings(env=raw)
    assert supplied.env == "development"
    assert supplied.env_was_explicit is False
    assert len(_warn_records(supplied)) == 1

    monkeypatch.setenv("IBEX_ENV", raw)
    from_env = Settings()
    assert from_env.env == "development"
    assert from_env.env_was_explicit is False
    assert len(_warn_records(from_env)) == 1


def test_allowed_hosts_parse_as_a_comma_separated_list() -> None:
    settings = Settings(allowed_hosts=" mcp.example.com , mcp.example.com:8443 ,")
    assert settings.allowed_host_list == ("mcp.example.com", "mcp.example.com:8443")
    assert Settings().allowed_host_list == ()
    assert Settings(allowed_origins="https://console.example.com").allowed_origin_list == (
        "https://console.example.com",
    )
