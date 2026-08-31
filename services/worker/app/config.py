"""Environment-backed worker configuration (IBEX_WORKER_* + shared Redis knobs)."""

from __future__ import annotations

import os
from functools import lru_cache
from urllib.parse import urlparse, urlunparse

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_QUEUE_NAMES: tuple[str, ...] = ("extraction", "embedding", "maintenance", "mcp_audit")


def redis_url_with_db(base_url: str, db_index: int) -> str:
    """Return *base_url* with its path replaced by ``/{db_index}``."""
    parsed = urlparse(base_url.strip())
    if parsed.scheme not in {"redis", "rediss", "unix"}:
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

    @field_validator("broker_url", "result_backend", "redis_url", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

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
    def _production_requires_redis(self) -> Settings:
        if self.env.lower() != "production":
            return self
        has_broker_env = bool(os.getenv("IBEX_WORKER_BROKER_URL", "").strip())
        has_redis_env = bool(
            os.getenv("REDIS_URL", "").strip()
            or os.getenv("IBEX_EXTRACTION_REDIS_URL", "").strip()
        )
        if not has_broker_env and not has_redis_env:
            msg = "IBEX_WORKER_BROKER_URL or REDIS_URL required when IBEX_ENV=production"
            raise ValueError(msg)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def queue_names() -> tuple[str, ...]:
    return _QUEUE_NAMES
