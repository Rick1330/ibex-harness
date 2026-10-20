"""Org-scoped operator-gateway calendar-minute rate limiter."""

from __future__ import annotations

from uuid import UUID

from mcp_gateway import RateLimitOutcome, RateLimitUnavailableError
from mcp_runtime.ratelimit import (
    INCR_EXPIRE_LUA,
    KEY_TTL_SECONDS,
    CalendarMinuteRateLimiter,
    NoopRateLimiter,
    RateLimitMetrics,
    RedisCalendarMinuteRateLimiter,
    build_rate_limit_metrics,
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


def _SPAN(name: str):
    return get_tracer().start_as_current_span(name)


class OperatorRateLimiter(CalendarMinuteRateLimiter[RateLimitOutcome]):
    pass


class NoopOperatorLimiter(NoopRateLimiter[RateLimitOutcome], OperatorRateLimiter):
    """Always allow — used when no Redis URL is configured."""

    def __init__(self, *, default_rpm: int = 120) -> None:
        NoopRateLimiter.__init__(self, default_rpm=default_rpm, result_factory=RateLimitOutcome)


class RedisOperatorLimiter(RedisCalendarMinuteRateLimiter[RateLimitOutcome], OperatorRateLimiter):
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
            key_scope="mcp_operator",
            default_rpm=default_rpm,
            org_overrides=org_overrides,
            owned=owned,
            fail_closed=fail_closed,
            unavailable_error=RateLimitUnavailableError,
            result_factory=RateLimitOutcome,
            metrics=METRICS,
            span=_SPAN,
            log_label="mcp operator",
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
        default_rpm=default_rpm,
        org_overrides=org_overrides,
        owned=True,
        fail_closed=fail_closed,
    )


def parse_org_rpm_overrides(raw: str) -> dict[UUID, int]:
    """Parse uuid=rpm,uuid2=rpm2 (same shape as IBEX_RATE_LIMIT_ORG_OVERRIDES)."""
    out: dict[UUID, int] = {}
    text = raw.strip()
    if not text:
        return out
    for pair in text.split(","):
        stripped = pair.strip()
        if stripped:
            org_id, rpm = _parse_org_rpm_pair(stripped)
            out[org_id] = rpm
    return out


def _parse_org_rpm_pair(pair: str) -> tuple[UUID, int]:
    org_s, sep, rpm_s = pair.partition("=")
    if not sep:
        msg = f"invalid pair {pair!r} (expected uuid=rpm)"
        raise ValueError(msg)
    return _parse_org_uuid(org_s, pair), _parse_rpm(rpm_s, pair)


def _parse_org_uuid(org_s: str, pair: str) -> UUID:
    try:
        return UUID(org_s.strip())
    except ValueError as exc:
        msg = f"invalid org UUID in {pair!r}"
        raise ValueError(msg) from exc


def _parse_rpm(rpm_s: str, pair: str) -> int:
    try:
        rpm = int(rpm_s.strip())
    except ValueError as exc:
        msg = f"invalid RPM in {pair!r}"
        raise ValueError(msg) from exc
    if rpm < 1:
        msg = f"invalid RPM in {pair!r}"
        raise ValueError(msg)
    return rpm
