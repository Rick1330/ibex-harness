"""Cache settings fields (IBEX_EMBEDDING_CACHE_* + REDIS_URL fallback)."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator


def _normalize_redis_url(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("redis URL must be non-empty when set")
    parsed = urlparse(stripped)
    scheme = parsed.scheme.lower()
    if scheme not in {"redis", "rediss", "unix"}:
        raise ValueError("redis URL scheme must be redis, rediss, or unix")
    if scheme != "unix" and not parsed.hostname:
        raise ValueError("redis URL must include a hostname")
    return stripped


class CacheEnvMixin(BaseModel):
    """Cache knobs composed into Settings. Env prefix comes from Settings."""

    cache_enabled: bool = Field(
        default=False,
        description="Wrap active backend with Redis content-hash cache",
    )
    cache_ttl_seconds: int = Field(
        default=86400,
        description="Redis TTL for cached embedding vectors (seconds)",
    )
    cache_redis_url: str | None = Field(
        default=None,
        description=(
            "Optional Redis URL override (IBEX_EMBEDDING_CACHE_REDIS_URL). "
            "Falls back to REDIS_URL when unset."
        ),
    )
    cache_redis_timeout_seconds: float = Field(
        default=0.1,
        description="Redis connect/read/write socket timeout (seconds)",
    )

    @model_validator(mode="after")
    def _fallback_redis_url(self) -> CacheEnvMixin:
        if self.cache_redis_url is not None:
            return self
        alias = os.environ.get("REDIS_URL", "").strip()
        if alias:
            self.cache_redis_url = _normalize_redis_url(alias)
        return self

    @field_validator("cache_redis_url")
    @classmethod
    def _check_cache_redis_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_redis_url(value)

    @field_validator("cache_ttl_seconds")
    @classmethod
    def _check_ttl(cls, value: int) -> int:
        if value < 1:
            raise ValueError("cache_ttl_seconds must be >= 1")
        return value

    @field_validator("cache_redis_timeout_seconds")
    @classmethod
    def _check_redis_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("cache_redis_timeout_seconds must be > 0")
        return value

    def resolved_cache_redis_url(self) -> str | None:
        """Return the effective Redis URL for the embedding cache, if any."""
        return self.cache_redis_url
