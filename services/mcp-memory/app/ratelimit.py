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
