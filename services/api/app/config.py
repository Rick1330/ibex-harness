"""Environment-backed management API configuration (IBEX_API_* + shared operator vars)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

CookieSameSite = Literal["lax", "strict", "none"]
_MIN_HMAC_SECRET_BYTES = 32


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

    # --- 4.P.0 operator topology (shared env names; see ENVIRONMENT_VARIABLES.md) ---
    allowed_origins: str = Field(
        default="http://localhost:3100",
        validation_alias=AliasChoices("IBEX_ALLOWED_ORIGINS", "IBEX_API_ALLOWED_ORIGINS"),
        description="Comma-separated CORS allow-list for the operator UI origin(s)",
    )
    shutdown_timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
        validation_alias=AliasChoices("IBEX_SHUTDOWN_TIMEOUT", "IBEX_API_SHUTDOWN_TIMEOUT"),
        description="SIGTERM drain budget for in-flight SSE (seconds)",
    )
    jwt_issuer: str = Field(
        default="ibex-harness",
        validation_alias=AliasChoices("JWT_ISSUER", "IBEX_API_JWT_ISSUER"),
    )
    jwt_audience: str = Field(
        default="ibex-dashboard",
        validation_alias=AliasChoices("JWT_AUDIENCE", "IBEX_API_JWT_AUDIENCE"),
    )
    jwt_access_token_ttl_seconds: int = Field(
        default=3600,
        ge=60,
        le=86_400,
        validation_alias=AliasChoices(
            "JWT_ACCESS_TOKEN_TTL_SECONDS", "IBEX_API_JWT_ACCESS_TOKEN_TTL_SECONDS"
        ),
    )
    jwt_refresh_token_ttl_seconds: int = Field(
        default=2_592_000,
        ge=60,
        le=31_536_000,
        validation_alias=AliasChoices(
            "JWT_REFRESH_TOKEN_TTL_SECONDS", "IBEX_API_JWT_REFRESH_TOKEN_TTL_SECONDS"
        ),
    )
    # Provisional HS256 secret for 4.P.0 stub only. 4.P.1 moves issuance to auth (RS256).
    # Do not alias JWT_PRIVATE_KEY_PEM — PEM must never be used as HMAC material.
    jwt_hmac_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("JWT_HMAC_SECRET", "IBEX_API_JWT_HMAC_SECRET"),
        description="Provisional HMAC secret for operator session JWTs (≥32 bytes when set)",
    )
    dashboard_session_cookie_name: str = Field(
        default="ibex_session",
        validation_alias=AliasChoices(
            "DASHBOARD_SESSION_COOKIE_NAME", "IBEX_API_DASHBOARD_SESSION_COOKIE_NAME"
        ),
    )
    dashboard_refresh_cookie_name: str = Field(
        default="ibex_refresh",
        validation_alias=AliasChoices(
            "DASHBOARD_REFRESH_COOKIE_NAME", "IBEX_API_DASHBOARD_REFRESH_COOKIE_NAME"
        ),
    )
    dashboard_csrf_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DASHBOARD_CSRF_SECRET", "IBEX_API_DASHBOARD_CSRF_SECRET"),
        description="HMAC key material for CSRF double-submit tokens",
    )
    dashboard_csrf_cookie_name: str = Field(
        default="ibex_csrf",
        validation_alias=AliasChoices(
            "DASHBOARD_CSRF_COOKIE_NAME", "IBEX_API_DASHBOARD_CSRF_COOKIE_NAME"
        ),
    )
    cookie_secure: bool = Field(
        default=False,
        validation_alias=AliasChoices("DASHBOARD_COOKIE_SECURE", "IBEX_API_COOKIE_SECURE"),
        description="Set Secure on session cookies (required true in staging/prod)",
    )
    cookie_samesite: CookieSameSite = Field(
        default="lax",
        validation_alias=AliasChoices("DASHBOARD_COOKIE_SAMESITE", "IBEX_API_COOKIE_SAMESITE"),
        description="lax|strict|none — none requires Secure; use for true cross-site only",
    )
    cookie_domain: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DASHBOARD_COOKIE_DOMAIN", "IBEX_API_COOKIE_DOMAIN"),
        description="Optional shared cookie domain (e.g. .ibexharness.com)",
    )
    sse_write_deadline_seconds: float = Field(
        default=15.0,
        ge=1.0,
        le=120.0,
        validation_alias=AliasChoices(
            "IBEX_API_SSE_WRITE_DEADLINE_SECONDS", "IBEX_SSE_WRITE_DEADLINE_SECONDS"
        ),
        description="Finite operator-event SSE write deadline (F4-033; stricter than provider)",
    )
    sse_slow_write_ms: int = Field(
        default=50,
        ge=1,
        validation_alias=AliasChoices("IBEX_API_SSE_SLOW_WRITE_MS", "IBEX_SSE_SLOW_WRITE_MS"),
    )
    operator_events_channel: str = Field(
        default="ibex:operator:events",
        validation_alias=AliasChoices(
            "IBEX_API_OPERATOR_EVENTS_CHANNEL", "IBEX_OPERATOR_EVENTS_CHANNEL"
        ),
        description="Redis pub/sub channel for operator-event fan-in",
    )
    # Default off until 4.P.1 RS256 issuer/verifier; enable explicitly for local smoke.
    operator_feature_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "IBEX_API_OPERATOR_FEATURE_ENABLED", "IBEX_OPERATOR_FEATURE_ENABLED"
        ),
        description="Kill switch: when false, operator session/SSE routes return 503",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def _empty_dsn_to_none(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("jwt_hmac_secret", mode="after")
    @classmethod
    def _require_hmac_length(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if len(value.encode("utf-8")) < _MIN_HMAC_SECRET_BYTES:
            raise ValueError(
                f"JWT_HMAC_SECRET must be at least {_MIN_HMAC_SECRET_BYTES} bytes when set"
            )
        return value

    @field_validator("cookie_samesite", mode="before")
    @classmethod
    def _normalize_samesite(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("cookie_samesite", mode="after")
    @classmethod
    def _validate_samesite(cls, value: str) -> CookieSameSite:
        if value not in ("lax", "strict", "none"):
            raise ValueError("DASHBOARD_COOKIE_SAMESITE must be lax, strict, or none")
        return value  # type: ignore[return-value]

    @field_validator("shutdown_timeout_seconds", mode="before")
    @classmethod
    def _parse_shutdown_timeout(cls, value: object) -> object:
        """Accept int seconds or Go-style durations like ``30s`` (ADR-0018 name reuse)."""
        if isinstance(value, str):
            raw = value.strip().lower()
            if raw.endswith("s") and raw[:-1].isdigit():
                return int(raw[:-1])
            if raw.isdigit():
                return int(raw)
        return value

    @model_validator(mode="after")
    def _reject_wildcard_origins(self) -> Settings:
        for part in self.allowed_origins.split(","):
            origin = part.strip()
            if origin == "*":
                raise ValueError(
                    "IBEX_ALLOWED_ORIGINS must not contain '*' when credentials are used"
                )
        return self

    @model_validator(mode="after")
    def _cookie_names_distinct(self) -> Settings:
        names = (
            self.dashboard_session_cookie_name.strip(),
            self.dashboard_refresh_cookie_name.strip(),
            self.dashboard_csrf_cookie_name.strip(),
        )
        if any(not n for n in names):
            raise ValueError("dashboard cookie names must be non-empty")
        if len(set(names)) != 3:
            raise ValueError("dashboard session, refresh, and CSRF cookie names must be distinct")
        if names != (
            self.dashboard_session_cookie_name,
            self.dashboard_refresh_cookie_name,
            self.dashboard_csrf_cookie_name,
        ):
            raise ValueError("dashboard cookie names must not include leading/trailing whitespace")
        return self

    def cors_origin_list(self) -> list[str]:
        return [part.strip() for part in self.allowed_origins.split(",") if part.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
