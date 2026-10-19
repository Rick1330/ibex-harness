"""Settings validation for the operator gateway (default-off, fail-closed)."""

from __future__ import annotations

from uuid import UUID

import pytest

from app.config import Settings, get_settings

ORG = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
        )


def test_production_requires_https_public_urls() -> None:
    with pytest.raises(ValueError, match="must use https"):
        Settings(
            enabled=True,
            env="production",
            database_url="postgresql+asyncpg://u:p@db/ibex",
            redis_url="redis://db:6379/0",
            resource_url="http://mcp.example.com/mcp",
            auth_server_url="https://auth.example.com",
        )


def test_production_rejects_loopback_host() -> None:
    with pytest.raises(ValueError, match="loopback host"):
        Settings(
            enabled=True,
            env="production",
            database_url="postgresql+asyncpg://u:p@db/ibex",
            redis_url="redis://db:6379/0",
            resource_url="https://127.0.0.1/mcp",
            auth_server_url="https://auth.example.com",
        )


def test_production_accepts_public_https() -> None:
    settings = Settings(
        enabled=True,
        env="production",
        database_url="postgresql+asyncpg://u:p@db/ibex",
        redis_url="redis://db:6379/0",
        resource_url="https://mcp.example.com/mcp",
        auth_server_url="https://auth.example.com",
        clickhouse_url="http://clickhouse.internal:8123",
    )
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
