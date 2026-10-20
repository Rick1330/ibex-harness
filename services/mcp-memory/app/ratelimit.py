"""Org-scoped MCP calendar-minute rate limiter (shared runtime twin)."""

from __future__ import annotations

from uuid import UUID

from mcp_runtime.ratelimit import (
    INCR_EXPIRE_LUA,
    KEY_TTL_SECONDS,
    CalendarMinuteRateLimiter,
    NoopRateLimiter,
    RateLimitResult,
    RedisCalendarMinuteRateLimiter,
    build_rate_limit_metrics,
    parse_org_rpm_overrides,
    redis_key,
)
from redis.asyncio import Redis

from app.errors import RateLimitUnavailableError

__all__ = [
    "INCR_EXPIRE_LUA",
    "KEY_TTL_SECONDS",
    "McpRateLimiter",
    "NoopMcpLimiter",
    "RateLimitResult",
    "RedisMcpLimiter",
    "build_mcp_rate_limiter",
    "parse_org_rpm_overrides",
]

METRICS = build_rate_limit_metrics(prefix="ibex_mcp", service="MCP")
RATE_LIMIT_ERRORS = METRICS.errors
RATE_LIMIT_REJECTED = METRICS.rejected


class McpRateLimiter(CalendarMinuteRateLimiter[RateLimitResult]):
    pass


class NoopMcpLimiter(NoopRateLimiter[RateLimitResult], McpRateLimiter):
    """Always allow — used when IBEX_MCP_REDIS_URL is unset."""

    def __init__(self, *, default_rpm: int = 120) -> None:
        NoopRateLimiter.__init__(self, default_rpm=default_rpm)


class RedisMcpLimiter(RedisCalendarMinuteRateLimiter[RateLimitResult], McpRateLimiter):
    def __init__(
        self,
        redis: Redis,
        *,
        default_rpm: int = 120,
        org_overrides: dict[UUID, int] | None = None,
        owned: bool = True,
        fail_closed: bool = False,
    ) -> None:
        RedisCalendarMinuteRateLimiter.__init__(
            self,
            redis,
            key_scope="mcp",
            default_rpm=default_rpm,
            org_overrides=org_overrides,
            owned=owned,
            fail_closed=fail_closed,
            unavailable_error=RateLimitUnavailableError,
            metrics=METRICS,
            log_label="mcp",
        )

    @staticmethod
    def redis_key(org_id: UUID, *, unix_minute: int | None = None) -> str:
        return redis_key("mcp", org_id, unix_minute=unix_minute)


def build_mcp_rate_limiter(
    *,
    redis_url: str,
    default_rpm: int,
    org_overrides: dict[UUID, int],
    fail_closed: bool = False,
) -> McpRateLimiter:
    url = redis_url.strip()
    if not url:
        return NoopMcpLimiter(default_rpm=default_rpm)
    client: Redis = Redis.from_url(url, decode_responses=True)
    return RedisMcpLimiter(
        client,
        default_rpm=default_rpm,
        org_overrides=org_overrides,
        owned=True,
        fail_closed=fail_closed,
    )
