"""Settings validation for the operator gateway (default-off, fail-closed)."""

from __future__ import annotations

import logging
from uuid import UUID

import pytest

from app.config import Settings, get_settings

ORG = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
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


def test_disabled_requires_no_dependencies() -> None:
    settings = Settings(enabled=False)
    assert settings.enabled is False
    assert settings.database_url == ""
    assert settings.protected_profile is False


def test_enabled_requires_database_url() -> None:
    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        Settings(enabled=True)


def test_defaults_are_loopback_and_http() -> None:
    settings = Settings(enabled=False)
    assert settings.host == "127.0.0.1"
    assert settings.port == 8091
    assert settings.resource_url == "http://127.0.0.1:8091/mcp"


def test_protected_profile_requires_redis() -> None:
    with pytest.raises(ValueError, match="REDIS_URL is required"):
        Settings(
            enabled=True,
            env="staging",
            database_url="postgresql+asyncpg://u:p@db/ibex",
            auth_grpc_ca_file="/etc/ibex/auth-grpc-ca.pem",
        )


def _production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "enabled": True,
        "env": "production",
        "database_url": "postgresql+asyncpg://u:p@db/ibex",
        "redis_url": "redis://db:6379/0",
        "resource_url": "https://mcp.example.com/mcp",
        "auth_server_url": "https://auth.example.com",
        # Present so the URL-validation cases reach the URL checks instead of
        # failing on the ADR-0097 §4 client CA requirement.
        "auth_grpc_ca_file": "/etc/ibex/auth-grpc-ca.pem",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_production_requires_https_public_urls() -> None:
    with pytest.raises(ValueError, match="must use https"):
        _production_settings(resource_url="http://mcp.example.com/mcp")


def test_production_rejects_loopback_host() -> None:
    with pytest.raises(ValueError, match="loopback host"):
        _production_settings(resource_url="https://127.0.0.1/mcp")


def test_production_accepts_public_https() -> None:
    settings = _production_settings(clickhouse_url="http://clickhouse.internal:8123")
    assert settings.protected_profile is True


def test_unknown_transport_setting_is_not_a_config_surface() -> None:
    settings = Settings(enabled=False, transport="stdio", allow_stdio=True)  # type: ignore[call-arg]
    assert not hasattr(settings, "transport")
    assert not hasattr(settings, "allow_stdio")


def test_org_override_map_parses() -> None:
    settings = Settings(enabled=False, rate_limit_org_overrides=f"{ORG}=42")
    assert settings.rate_limit_org_override_map == {ORG: 42}


def test_bad_org_override_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="expected uuid=rpm"):
        Settings(enabled=False, rate_limit_org_overrides="broken")


def test_enabled_protected_profile_requires_auth_ca() -> None:
    kwargs = {
        "enabled": True,
        "env": "staging",
        "database_url": "postgresql://ibex@postgres/ibex",
        "redis_url": "redis://redis:6379/0",
    }
    with pytest.raises(ValueError, match="IBEX_AUTH_GRPC_CA_FILE"):
        Settings(**kwargs)
    with pytest.raises(ValueError, match="IBEX_AUTH_GRPC_CA_FILE"):
        Settings(**kwargs, auth_grpc_ca_file="   ")
    Settings(**kwargs, auth_grpc_ca_file="/etc/ibex/auth-grpc-ca.pem")


def test_unset_env_warns_about_the_relaxed_posture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IBEX_ENV", raising=False)
    monkeypatch.delenv("IBEX_MCP_OPERATOR_ENV", raising=False)
    settings = Settings(enabled=False)
    assert settings.env == "development"
    assert settings.env_was_explicit is False
    records = _warn_records(settings)
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert "IBEX_ENV is not set" in records[0].getMessage()


def test_explicit_env_does_not_warn() -> None:
    settings = Settings(enabled=False, env="development")
    assert settings.env_was_explicit is True
    assert _warn_records(settings) == []


@pytest.mark.parametrize("raw", ["", " ", "\t\n "])
def test_blank_env_is_treated_as_unset(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    # A blank IBEX_ENV counted as explicit: it was coerced to development and
    # suppressed the relaxed-posture warning.
    monkeypatch.delenv("IBEX_ENV", raising=False)
    monkeypatch.delenv("IBEX_MCP_OPERATOR_ENV", raising=False)
    supplied = Settings(enabled=False, env=raw)
    assert supplied.env == "development"
    assert supplied.env_was_explicit is False
    assert len(_warn_records(supplied)) == 1

    monkeypatch.setenv("IBEX_ENV", raw)
    from_env = Settings(enabled=False)
    assert from_env.env == "development"
    assert from_env.env_was_explicit is False
    assert len(_warn_records(from_env)) == 1


def test_allowed_hosts_parse_as_a_comma_separated_list() -> None:
    settings = Settings(enabled=False, allowed_hosts=" a.example , b.example ,")
    assert settings.allowed_host_list == ("a.example", "b.example")
    assert Settings(enabled=False).allowed_origin_list == ()
