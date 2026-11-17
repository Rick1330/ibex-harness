"""Environment-backed configuration for the read-only MCP operator gateway.

``IBEX_ENV`` defaults to ``development``. The gateway is inert unless
``IBEX_MCP_OPERATOR_ENABLED=true``; a disabled profile has no database, Redis, or
public-URL requirements because it exposes no surface.
"""

from __future__ import annotations

import ipaddress
import logging
from functools import lru_cache
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.ratelimit import parse_org_rpm_overrides

_LOOPBACK_DNS = frozenset({"localhost"})
_PROTECTED_ENVS = frozenset({"staging", "production"})

# Same reasoning as services/mcp-memory/app/config.py: the default is kept
# because every local run and the unit suite start without IBEX_ENV, and what
# was missing is the signal that the posture relaxed.
_ENV_FALLBACK_WARNING = (
    "IBEX_ENV is not set; falling back to 'development'. This relaxes three "
    "controls: DNS-rebinding protection is disabled (test hosts are accepted), "
    "loopback discovery URLs are allowed, and no AuthService CA is required, so "
    "the gRPC connection may be plaintext. Set IBEX_ENV=staging or production "
    "for anything another host can reach."
)


# Every name a blank IBEX_ENV can arrive under: the field name through
# ``populate_by_name``, and the two aliases. A blank value used to be coerced to
# ``development`` by ``_check_env`` while still counting as explicit, so the
# relaxed-posture warning never fired.
_ENV_INPUT_KEYS = frozenset({"env", "IBEX_ENV", "IBEX_MCP_OPERATOR_ENV"})


def parse_name_list(raw: str) -> tuple[str, ...]:
    """Split a comma-separated allow-list, dropping blanks and keeping order."""
    return tuple(part.strip() for part in raw.split(",") if part.strip())


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
    auth_grpc_ca_file: str | None = Field(
        default=None,
        validation_alias="IBEX_AUTH_GRPC_CA_FILE",
        description="CA bundle PEM used to verify AuthService gRPC TLS (ADR-0097 §4); "
        "unset keeps the trust-gated plaintext dial",
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
    # P1-14: extra Host/Origin values for DNS-rebinding protection. The gateway
    # already derives its own host from resource_url; this list adds aliases an
    # operator reaches it by (a second DNS name, an IPv6 literal, a port the
    # proxy preserves). It defaults to empty, and the derived host is what makes
    # a configured deployment work.
    allowed_hosts: str = Field(
        default="",
        validation_alias=AliasChoices("IBEX_MCP_ALLOWED_HOSTS", "IBEX_MCP_OPERATOR_ALLOWED_HOSTS"),
        description="Comma-separated extra Host values for DNS-rebinding protection",
    )
    allowed_origins: str = Field(
        default="",
        validation_alias=AliasChoices(
            "IBEX_MCP_ALLOWED_ORIGINS", "IBEX_MCP_OPERATOR_ALLOWED_ORIGINS"
        ),
        description="Comma-separated Origin values for DNS-rebinding protection",
    )
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

    @property
    def allowed_host_list(self) -> tuple[str, ...]:
        return parse_name_list(self.allowed_hosts)

    @property
    def allowed_origin_list(self) -> tuple[str, ...]:
        return parse_name_list(self.allowed_origins)

    @property
    def env_was_explicit(self) -> bool:
        """True when IBEX_ENV was supplied rather than defaulted."""
        return "env" in self.model_fields_set

    def warn_if_env_defaulted(self, log: logging.Logger) -> None:
        """Log the relaxed posture once when IBEX_ENV was not supplied."""
        if not self.env_was_explicit:
            log.warning(_ENV_FALLBACK_WARNING)

    @model_validator(mode="before")
    @classmethod
    def _drop_blank_env(cls, data: object) -> object:
        """Treat a blank IBEX_ENV as unset, so the default and its warning apply."""
        if not isinstance(data, dict):
            return data
        blank = {
            key
            for key in _ENV_INPUT_KEYS
            if isinstance(data.get(key), str) and not data[key].strip()
        }
        if not blank:
            return data
        return {key: value for key, value in data.items() if key not in blank}

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
        _require_auth_ca_outside_development(self.env, self.auth_grpc_ca_file)
        self._require_dependencies()
        if self.env != "production":
            return self
        self._require_public_https("IBEX_MCP_OPERATOR_RESOURCE_URL", self.resource_url)
        self._require_public_https("IBEX_MCP_OPERATOR_AUTH_SERVER_URL", self.auth_server_url)
        return self

    def _require_dependencies(self) -> None:
        if not self.database_url.strip():
            raise ValueError("IBEX_MCP_OPERATOR_DATABASE_URL is required when enabled")
        if self.protected_profile and not self.redis_url.strip():
            raise ValueError("IBEX_MCP_OPERATOR_REDIS_URL is required in protected profiles")

    @staticmethod
    def _require_public_https(name: str, value: str) -> None:
        parts = urlsplit(value.strip())
        host = (parts.hostname or "").lower().rstrip(".")
        if parts.scheme.lower() != "https":
            raise ValueError(f"{name} must use https in production")
        if not host or _is_loopback_host(host):
            raise ValueError(f"{name} must not use a loopback host in production")


def _require_auth_ca_outside_development(environment: str, ca_file: str | None) -> None:
    """Outside development the AuthService CA is mandatory (ADR-0097 §4)."""
    if environment == "development":
        return
    if not (ca_file or "").strip():
        raise ValueError(
            "IBEX_AUTH_GRPC_CA_FILE is required outside development; "
            "plaintext AuthService connections are not allowed"
        )


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
