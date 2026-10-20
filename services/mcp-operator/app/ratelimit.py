"""Org-scoped operator-gateway calendar-minute rate limiter."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from mcp_gateway import RateLimitOutcome, RateLimitUnavailableError
from mcp_runtime.ratelimit import (
    INCR_EXPIRE_LUA,
    KEY_TTL_SECONDS,
    CalendarMinuteRateLimiter,
    NoopRateLimiter,
    RateLimitMetrics,
    RedisCalendarMinuteRateLimiter,
    RedisLimiterConfig,
    build_rate_limit_metrics,
    parse_org_rpm_overrides,
    redis_key,
)
from redis.asyncio import Redis

from app.dependency_metrics import REDIS_DURATION
from app.tracing import get_tracer

__all__ = [
    "INCR_EXPIRE_LUA",
    "KEY_TTL_SECONDS",
    "NoopOperatorLimiter",
    "OperatorRateLimiter",
    "RedisOperatorLimiter",
    "build_operator_rate_limiter",
    "parse_org_rpm_overrides",
]

METRICS = build_rate_limit_metrics(prefix="ibex_mcp_operator", service="Operator gateway")
METRICS = RateLimitMetrics(
    errors=METRICS.errors,
    rejected=METRICS.rejected,
    duration=REDIS_DURATION.observe,
)
RATE_LIMIT_ERRORS = METRICS.errors
RATE_LIMIT_REJECTED = METRICS.rejected


def _span(name: str):
    return get_tracer().start_as_current_span(name)


class OperatorRateLimiter(CalendarMinuteRateLimiter[RateLimitOutcome]):
    pass


class NoopOperatorLimiter(NoopRateLimiter[RateLimitOutcome], OperatorRateLimiter):
    """Always allow — used when no Redis URL is configured."""

    def __init__(self, *, default_rpm: int = 120) -> None:
        NoopRateLimiter.__init__(self, default_rpm=default_rpm, result_factory=RateLimitOutcome)


@dataclass(frozen=True, slots=True)
class OperatorLimiterOptions:
    default_rpm: int = 120
    org_overrides: dict[UUID, int] | None = None
    owned: bool = True
    fail_closed: bool = False


class RedisOperatorLimiter(RedisCalendarMinuteRateLimiter[RateLimitOutcome], OperatorRateLimiter):
    def __init__(self, redis: Redis, *, options: OperatorLimiterOptions | None = None) -> None:
        opts = options or OperatorLimiterOptions()
        RedisCalendarMinuteRateLimiter.__init__(
            self,
            redis,
            config=RedisLimiterConfig(
                key_scope="mcp_operator",
                default_rpm=opts.default_rpm,
                org_overrides=opts.org_overrides,
                owned=opts.owned,
                fail_closed=opts.fail_closed,
                unavailable_error=RateLimitUnavailableError,
                result_factory=RateLimitOutcome,
                metrics=METRICS,
                span=_span,
                log_label="mcp operator",
            ),
        )

    @staticmethod
    def redis_key(org_id: UUID, *, unix_minute: int | None = None) -> str:
        return redis_key("mcp_operator", org_id, unix_minute=unix_minute)


def build_operator_rate_limiter(
    *,
    redis_url: str,
    default_rpm: int,
    org_overrides: dict[UUID, int],
    fail_closed: bool = False,
) -> OperatorRateLimiter:
    url = redis_url.strip()
    if not url:
        return NoopOperatorLimiter(default_rpm=default_rpm)
    client: Redis = Redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
    )
    return RedisOperatorLimiter(
        client,
        options=OperatorLimiterOptions(
            default_rpm=default_rpm,
            org_overrides=org_overrides,
            owned=True,
            fail_closed=fail_closed,
        ),
    )
