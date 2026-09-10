"""Environment-backed management API configuration (IBEX_API_*)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IBEX_API_",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8010, description="Bind port")

    database_url: str | None = Field(
        default=None,
        description="Async Postgres DSN (postgresql+asyncpg://...)",
    )

    auth_grpc_addr: str = Field(
        default="127.0.0.1:9091",
        validation_alias=AliasChoices("IBEX_AUTH_GRPC_ADDR", "IBEX_API_AUTH_GRPC_ADDR"),
        description="Auth service gRPC target for ValidateToken",
    )
    auth_timeout_ms: int = Field(default=50, ge=1)

    redis_url: str | None = Field(
        default=None,
        description="Redis URL for org_suspend + rate-limit config pub/sub (optional; best-effort)",
    )
    rate_limit_default_rpm: int = Field(
        default=60,
        ge=1,
        le=1_000_000,
        description="Platform default org/agent RPM when no override row exists",
    )
    celery_broker_url: str | None = Field(
        default=None,
        description="Celery broker URL for org deletion enqueue (optional)",
    )

    docs_base_url: str = Field(
        default="https://docs.ibexharness.com",
        description="Base URL for error docs_url links",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def _empty_dsn_to_none(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
