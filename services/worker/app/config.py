"""Environment-backed worker configuration (IBEX_WORKER_* + shared Redis knobs)."""

from __future__ import annotations

import os
from functools import lru_cache
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_QUEUE_NAMES: tuple[str, ...] = ("extraction", "embedding", "maintenance", "mcp_audit")
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def require_https_or_loopback(url: str | None) -> str | None:
    """Remote extraction URLs must be HTTPS; HTTP is allowed only on loopback."""
    if url is None:
        return None
    trimmed = url.strip()
    parsed = urlparse(trimmed)
    host = parsed.hostname
    if host is None:
        raise ValueError(
            "extraction base URL must include a hostname "
            "(https:// or http:// on loopback)"
        )
    host = host.lower()
    if parsed.scheme == "https":
        return trimmed
    if parsed.scheme == "http" and host in _LOOPBACK_HOSTS:
        return trimmed
    raise ValueError(
        "extraction base URL must use https:// or http:// on loopback "
        "(127.0.0.1, localhost, ::1)"
    )


def redis_url_with_db(base_url: str, db_index: int) -> str:
    """Return Redis URL with logical DB *db_index* applied.

    - ``redis://`` / ``rediss://`` — replace path ``/{db}``
    - ``unix://`` — convert to Celery ``redis+socket://`` with ``virtual_host``
    """
    parsed = urlparse(base_url.strip())
    if parsed.scheme == "unix":
        socket_path = parsed.path
        query = parse_qs(parsed.query)
        query["virtual_host"] = [str(db_index)]
        return f"redis+socket://{socket_path}?{urlencode(query, doseq=True)}"
    if parsed.scheme not in {"redis", "rediss"}:
        msg = f"unsupported Redis URL scheme: {parsed.scheme!r}"
        raise ValueError(msg)
    return urlunparse(parsed._replace(path=f"/{db_index}"))


class Settings(BaseSettings):
    """Celery worker settings."""

    model_config = SettingsConfigDict(
        env_prefix="IBEX_WORKER_",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    env: str = Field(
        default="development",
        validation_alias=AliasChoices("IBEX_ENV", "IBEX_WORKER_ENV"),
        description="Runtime environment (production enforces broker URL)",
    )

    broker_url: str | None = Field(
        default=None,
        description="Full Celery broker URL override",
    )
    result_backend: str | None = Field(
        default=None,
        description="Full Celery result-backend URL override",
    )

    redis_url: str = Field(
        default="redis://127.0.0.1:6379/0",
        validation_alias=AliasChoices(
            "IBEX_EXTRACTION_REDIS_URL",
            "REDIS_URL",
            "IBEX_WORKER_REDIS_URL",
        ),
        description="Shared Redis base URL used to derive broker/result URLs",
    )
    redis_db_queue: int = Field(
        default=1,
        ge=0,
        le=15,
        validation_alias=AliasChoices("REDIS_DB_QUEUE", "IBEX_WORKER_REDIS_DB_QUEUE"),
        description="Redis logical DB for Celery broker lists",
    )
    redis_db_results: int = Field(
        default=3,
        ge=0,
        le=15,
        validation_alias=AliasChoices("REDIS_DB_RESULTS", "IBEX_WORKER_REDIS_DB_RESULTS"),
        description="Redis logical DB for Celery result backend keys",
    )

    maintenance_beat_seconds: float = Field(
        default=300.0,
        gt=0,
        description="Interval for maintenance noop beat sweep",
    )
    result_expires_seconds: int = Field(
        default=3600,
        ge=60,
        description="TTL for stored task results when ignore_result=False",
    )
    worker_concurrency: int = Field(default=4, ge=1)
    worker_prefetch_multiplier: int = Field(default=4, ge=1)
    worker_max_tasks_per_child: int = Field(default=1000, ge=1)
    worker_hostname: str = Field(
        default="ibex-worker@%h",
        description="Stable Celery nodename (%h expands to hostname)",
    )
    beat_schedule_file: str = Field(
        default="/var/lib/ibex/celerybeat/celerybeat-schedule",
        description="Path for Celery beat schedule persistence",
    )
    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "POSTGRES_DSN",
            "IBEX_WORKER_DATABASE_URL",
        ),
        description="Postgres DSN for dead-letter persistence (asyncpg SQLAlchemy URL)",
    )
    metrics_port: int = Field(
        default=8006,
        ge=1024,
        le=65535,
        validation_alias=AliasChoices("IBEX_WORKER_METRICS_PORT"),
        description="Prometheus /metrics HTTP port for worker process",
    )
    enqueue_port: int = Field(
        default=8007,
        ge=1024,
        le=65535,
        validation_alias=AliasChoices("IBEX_WORKER_ENQUEUE_PORT"),
        description="Internal Starlette port for POST /internal/extraction/enqueue",
    )
    enqueue_host: str = Field(
        default="127.0.0.1",
        validation_alias=AliasChoices("IBEX_WORKER_ENQUEUE_HOST"),
        description="Bind host for enqueue HTTP (containers set 0.0.0.0 explicitly)",
    )
    enqueue_api_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("IBEX_WORKER_ENQUEUE_API_TOKEN"),
        description="Static Bearer token for proxy→worker extraction enqueue",
    )
    extraction_provider: str = Field(
        default="openai",
        validation_alias=AliasChoices(
            "IBEX_WORKER_EXTRACTION_PROVIDER",
            "EXTRACTION_PROVIDER",
        ),
        description="Extraction LLM backend: openai | vllm (startup-once)",
    )
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "OPENAI_API_KEY",
            "IBEX_WORKER_OPENAI_API_KEY",
        ),
        description="Bearer token for hosted OpenAI extraction",
    )
    extraction_openai_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices(
            "IBEX_WORKER_EXTRACTION_OPENAI_MODEL",
            "EXTRACTION_OPENAI_MODEL",
        ),
        description="OpenAI model id for extraction",
    )
    extraction_openai_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "IBEX_WORKER_EXTRACTION_OPENAI_BASE_URL",
        ),
        description="OpenAI-compatible base URL (default api.openai.com/v1)",
    )
    extraction_vllm_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "IBEX_WORKER_EXTRACTION_VLLM_BASE_URL",
            "IBEX_WORKER_EXTRACTION_BASE_URL",
            "EXTRACTION_BASE_URL",
        ),
        description="vLLM OpenAI-compatible base URL (required when provider=vllm)",
    )
    extraction_vllm_model: str = Field(
        default="Qwen2.5-14B-Instruct",
        validation_alias=AliasChoices(
            "IBEX_WORKER_EXTRACTION_VLLM_MODEL",
            "EXTRACTION_VLLM_MODEL",
        ),
        description="vLLM served model id",
    )
    extraction_vllm_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("IBEX_WORKER_EXTRACTION_VLLM_API_KEY"),
        description="Optional vLLM key; omitted from Authorization when empty",
    )
    extraction_timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        le=180,
        validation_alias=AliasChoices("IBEX_WORKER_EXTRACTION_TIMEOUT_SECONDS"),
        description="HTTP timeout for extraction chat-completions",
    )
    memory_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "IBEX_WORKER_MEMORY_BASE_URL",
            "MEMORY_BASE_URL",
        ),
        description="Memory service origin for POST /v1/memories",
    )
    memory_api_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "IBEX_WORKER_MEMORY_API_TOKEN",
            "MEMORY_API_TOKEN",
        ),
        description="Bearer token with memory:write for extraction writes",
    )
    clickhouse_dsn: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "CLICKHOUSE_DSN",
            "IBEX_WORKER_CLICKHOUSE_DSN",
        ),
        description="ClickHouse HTTP DSN for llm_traces; empty skips insert",
    )

    @field_validator(
        "broker_url",
        "result_backend",
        "database_url",
        "extraction_openai_base_url",
        "extraction_vllm_base_url",
        "memory_base_url",
        "clickhouse_dsn",
        mode="before",
    )
    @classmethod
    def _empty_optional_to_none(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("redis_url", mode="before")
    @classmethod
    def _empty_redis_to_default(cls, value: object) -> object:
        if value is None:
            return "redis://127.0.0.1:6379/0"
        if isinstance(value, str) and not value.strip():
            return "redis://127.0.0.1:6379/0"
        return value

    @field_validator("extraction_openai_base_url", "extraction_vllm_base_url")
    @classmethod
    def _https_or_loopback_extraction_url(cls, value: str | None) -> str | None:
        return require_https_or_loopback(value)

    @property
    def resolved_broker_url(self) -> str:
        if self.broker_url:
            return self.broker_url
        return redis_url_with_db(self.redis_url, self.redis_db_queue)

    @property
    def resolved_result_backend(self) -> str:
        if self.result_backend:
            return self.result_backend
        return redis_url_with_db(self.redis_url, self.redis_db_results)

    @model_validator(mode="after")
    def _enqueue_metrics_ports_differ(self) -> Settings:
        token = self.enqueue_api_token
        if token is None or not token.get_secret_value().strip():
            return self
        if self.enqueue_port == self.metrics_port:
            msg = "enqueue_port and metrics_port must differ when enqueue API token is set"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _production_requires_redis(self) -> Settings:
        if self.env.lower() != "production":
            return self
        has_broker_env = bool(os.getenv("IBEX_WORKER_BROKER_URL", "").strip())
        has_redis_env = bool(
            os.getenv("REDIS_URL", "").strip()
            or os.getenv("IBEX_EXTRACTION_REDIS_URL", "").strip()
            or os.getenv("IBEX_WORKER_REDIS_URL", "").strip()
        )
        if not has_broker_env and not has_redis_env:
            msg = (
                "IBEX_WORKER_BROKER_URL or REDIS_URL / IBEX_EXTRACTION_REDIS_URL / "
                "IBEX_WORKER_REDIS_URL required when IBEX_ENV=production"
            )
            raise ValueError(msg)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def queue_names() -> tuple[str, ...]:
    return _QUEUE_NAMES
