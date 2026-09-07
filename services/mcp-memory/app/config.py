"""Environment-backed MCP service configuration (IBEX_MCP_* + IBEX_AUTH_GRPC_ADDR)."""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.ratelimit import parse_org_rpm_overrides

TRANSPORT_HTTP = "streamable_http"
TRANSPORT_STDIO = "stdio"
_ALLOWED_TRANSPORTS = frozenset({TRANSPORT_HTTP, TRANSPORT_STDIO})
_LOOPBACK_DNS = frozenset({"localhost"})


class Settings(BaseSettings):
    """MCP skeleton settings. Secrets are never logged by callers."""

    model_config = SettingsConfigDict(
        env_prefix="IBEX_MCP_",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    env: str = Field(
        default="development",
        validation_alias=AliasChoices("IBEX_ENV", "IBEX_MCP_ENV"),
    )
    transport: str = Field(default=TRANSPORT_HTTP)
    allow_stdio: bool = Field(default=False)
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8090, ge=1, le=65535)
    resource_url: str = Field(default="http://127.0.0.1:8090/mcp")
    auth_server_url: str = Field(default="http://127.0.0.1:8080")
    auth_grpc_addr: str = Field(
        default="127.0.0.1:9091",
        validation_alias=AliasChoices("IBEX_AUTH_GRPC_ADDR", "IBEX_MCP_AUTH_GRPC_ADDR"),
    )
    auth_timeout_ms: int = Field(default=50, ge=1, le=5000)
    clickhouse_url: str = Field(default="")
    audit_queue_size: int = Field(default=1024, ge=1, le=100_000)
    # Memory HTTP for 3.5.E.2 tools (search/write). Empty → tool calls fail closed.
    memory_http_url: str = Field(
        default="",
        validation_alias=AliasChoices("IBEX_MEMORY_HTTP_URL", "IBEX_MCP_MEMORY_HTTP_URL"),
    )
    memory_timeout_ms: int = Field(
        default=5000,
        ge=1,
        le=60_000,
        validation_alias=AliasChoices("IBEX_MCP_MEMORY_TIMEOUT_MS", "IBEX_MEMORY_TIMEOUT_MS"),
    )
    redis_url: str = Field(
        default="",
        validation_alias=AliasChoices("IBEX_MCP_REDIS_URL", "REDIS_URL"),
    )
    rate_limit_rpm: int = Field(default=120, ge=1, le=1_000_000)
    rate_limit_org_overrides: str = Field(default="")

    @property
    def rate_limit_org_override_map(self) -> dict[UUID, int]:
        return parse_org_rpm_overrides(self.rate_limit_org_overrides)

    @field_validator("transport")
    @classmethod
    def _check_transport(cls, value: str) -> str:
        stripped = value.strip().lower()
        if stripped not in _ALLOWED_TRANSPORTS:
            raise ValueError("IBEX_MCP_TRANSPORT must be streamable_http or stdio")
        return stripped

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
    def _check_discovery_urls(self) -> Settings:
        """Production must advertise non-loopback HTTPS discovery URLs."""
        if self.env != "production":
            return self
        self._require_public_https("IBEX_MCP_RESOURCE_URL", self.resource_url)
        self._require_public_https("IBEX_MCP_AUTH_SERVER_URL", self.auth_server_url)
        # Empty memory URL remains allowed (tools fail closed); non-empty must be public HTTPS.
        if self.memory_http_url.strip():
            self._require_public_https("IBEX_MEMORY_HTTP_URL", self.memory_http_url)
        return self

    @staticmethod
    def _require_public_https(name: str, value: str) -> None:
        parts = urlsplit(value.strip())
        host = (parts.hostname or "").lower().rstrip(".")
        if parts.scheme.lower() != "https":
            raise ValueError(f"{name} must use https in production")
        if not host or _is_loopback_host(host):
            raise ValueError(f"{name} must not use a loopback host in production")

    def validate_transport_policy(self) -> None:
        """Refuse stdio unless explicitly enabled and not production."""
        if self.transport != TRANSPORT_STDIO:
            return
        if self.env == "production":
            raise ValueError("stdio MCP transport is forbidden when IBEX_ENV=production")
        if not self.allow_stdio:
            raise ValueError("stdio MCP transport requires IBEX_MCP_ALLOW_STDIO=true")


def _is_loopback_host(host: str) -> bool:
    """True for localhost DNS and any loopback IPv4/IPv6 literal (incl. 127.0.0.2)."""
    normalized = host.lower().rstrip(".")
    if normalized in _LOOPBACK_DNS:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_transport_policy()
    return settings
