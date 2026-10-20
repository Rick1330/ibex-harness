"""Environment-backed configuration for the read-only MCP operator gateway.

``IBEX_ENV`` defaults to ``development``. The gateway is inert unless
``IBEX_MCP_OPERATOR_ENABLED=true``; a disabled profile has no database, Redis, or
public-URL requirements because it exposes no surface.
"""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.ratelimit import parse_org_rpm_overrides

_LOOPBACK_DNS = frozenset({"localhost"})
_PROTECTED_ENVS = frozenset({"staging", "production"})


class Settings(BaseSettings):
    """MCP operator gateway settings. Secrets are never logged by callers."""

    model_config = SettingsConfigDict(
        env_prefix="IBEX_MCP_OPERATOR_",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    env: str = Field(
        default="development",
        validation_alias=AliasChoices("IBEX_ENV", "IBEX_MCP_OPERATOR_ENV"),
    )
    enabled: bool = Field(default=False)
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8091, ge=1, le=65535)
    resource_url: str = Field(default="http://127.0.0.1:8091/mcp")
    auth_server_url: str = Field(default="http://127.0.0.1:8080")
    auth_grpc_addr: str = Field(
        default="127.0.0.1:9091",
        validation_alias=AliasChoices("IBEX_AUTH_GRPC_ADDR", "IBEX_MCP_OPERATOR_AUTH_GRPC_ADDR"),
    )
    auth_timeout_ms: int = Field(default=50, ge=1, le=5000)
    database_url: str = Field(
        default="",
        validation_alias=AliasChoices("IBEX_MCP_OPERATOR_DATABASE_URL", "IBEX_DATABASE_URL"),
    )
    redis_url: str = Field(
        default="",
        validation_alias=AliasChoices("IBEX_MCP_OPERATOR_REDIS_URL", "REDIS_URL"),
    )
    rate_limit_rpm: int = Field(default=120, ge=1, le=1_000_000)
    rate_limit_org_overrides: str = Field(default="")
    clickhouse_url: str = Field(default="")
    audit_queue_size: int = Field(default=1024, ge=1, le=100_000)
    otel_endpoint: str = Field(
        default="",
        validation_alias=AliasChoices(
            "IBEX_OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT"
        ),
    )

    @property
    def rate_limit_org_override_map(self) -> dict[UUID, int]:
        return parse_org_rpm_overrides(self.rate_limit_org_overrides)

    @property
    def protected_profile(self) -> bool:
        return self.env in _PROTECTED_ENVS

    @field_validator("env")
    @classmethod
    def _check_env(cls, value: str) -> str:
        return value.strip().lower() or "development"

    @field_validator("rate_limit_org_overrides")
    @classmethod
    def _check_org_overrides(cls, value: str) -> str:
        parse_org_rpm_overrides(value)
        return value

    @model_validator(mode="after")
    def _check_requirements(self) -> Settings:
        if not self.enabled:
            # A disabled gateway exposes no surface, so no dependency is required.
            return self
        if not self.database_url.strip():
            raise ValueError("IBEX_MCP_OPERATOR_DATABASE_URL is required when enabled")
        if self.protected_profile and not self.redis_url.strip():
            raise ValueError("IBEX_MCP_OPERATOR_REDIS_URL is required in protected profiles")
        if self.env != "production":
            return self
        self._require_public_https("IBEX_MCP_OPERATOR_RESOURCE_URL", self.resource_url)
        self._require_public_https("IBEX_MCP_OPERATOR_AUTH_SERVER_URL", self.auth_server_url)
        return self

    @staticmethod
    def _require_public_https(name: str, value: str) -> None:
        parts = urlsplit(value.strip())
        host = (parts.hostname or "").lower().rstrip(".")
        if parts.scheme.lower() != "https":
            raise ValueError(f"{name} must use https in production")
        if not host or _is_loopback_host(host):
            raise ValueError(f"{name} must not use a loopback host in production")


def _is_loopback_host(host: str) -> bool:
    """True for localhost DNS and any loopback IPv4/IPv6 literal."""
    normalized = host.lower().rstrip(".")
    if normalized in _LOOPBACK_DNS:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
