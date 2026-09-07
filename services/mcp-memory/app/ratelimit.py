"""Org-scoped MCP calendar-minute rate limiter (Python twin of packages/ratelimit).

Mirrors packages/ratelimit/window.go semantics: Lua INCR + EXPIRE-on-create (90s),
key ratelimit:{org_id}:mcp:{unix_minute}. Fail-open on Redis errors.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from prometheus_client import Counter
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

KEY_TTL_SECONDS = 90

# Mirrors packages/ratelimit/window.go incrExpireLua exactly.
INCR_EXPIRE_LUA = """
local n = redis.call("INCR", KEYS[1])
if n == 1 then
  redis.call("EXPIRE", KEYS[1], ARGV[1])
end
return n
"""

RATE_LIMIT_ERRORS = Counter(
    "ibex_mcp_rate_limit_errors_total",
    "MCP rate-limit Redis failures (fail-open admits the request)",
)
RATE_LIMIT_REJECTED = Counter(
    "ibex_mcp_rate_limit_rejected_total",
    "MCP tool calls rejected for exceeding org RPM",
)


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_unix: int


class McpRateLimiter(ABC):
    @abstractmethod
    async def check(self, org_id: UUID) -> RateLimitResult:
        raise NotImplementedError


class NoopMcpLimiter(McpRateLimiter):
    """Always allow — used when IBEX_MCP_REDIS_URL is unset."""

    def __init__(self, *, default_rpm: int = 120) -> None:
        self._default_rpm = max(1, default_rpm)

    async def check(self, org_id: UUID) -> RateLimitResult:
        del org_id
        now = int(time.time())
        reset = ((now // 60) + 1) * 60
        return RateLimitResult(
            allowed=True,
            limit=self._default_rpm,
            remaining=self._default_rpm,
            reset_unix=reset,
        )


class RedisMcpLimiter(McpRateLimiter):
    def __init__(
        self,
        redis: Redis,
        *,
        default_rpm: int = 120,
        org_overrides: dict[UUID, int] | None = None,
        owned: bool = True,
    ) -> None:
        self._redis = redis
        self._default_rpm = max(1, default_rpm)
        self._org_overrides = org_overrides or {}
        self._owned = owned
        self._script = self._redis.register_script(INCR_EXPIRE_LUA)

    def effective_limit(self, org_id: UUID) -> int:
        override = self._org_overrides.get(org_id)
        if override is not None and override > 0:
            return override
        return self._default_rpm

    @staticmethod
    def redis_key(org_id: UUID, *, unix_minute: int | None = None) -> str:
        minute = unix_minute if unix_minute is not None else int(time.time()) // 60
        return f"ratelimit:{org_id}:mcp:{minute}"

    async def check(self, org_id: UUID) -> RateLimitResult:
        limit = self.effective_limit(org_id)
        now = int(time.time())
        unix_minute = now // 60
        reset_unix = (unix_minute + 1) * 60
        key = self.redis_key(org_id, unix_minute=unix_minute)
        try:
            count = int(
                await self._script(keys=[key], args=[KEY_TTL_SECONDS])
            )
        except (OSError, RedisError) as exc:
            RATE_LIMIT_ERRORS.inc()
            logger.warning(
                "mcp rate limit redis fail-open org_id=%s error_class=%s",
                org_id,
                type(exc).__name__,
            )
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=limit,
                reset_unix=reset_unix,
            )
        remaining = max(0, limit - count)
        if count > limit:
            RATE_LIMIT_REJECTED.inc()
            return RateLimitResult(
                allowed=False,
                limit=limit,
                remaining=0,
                reset_unix=reset_unix,
            )
        return RateLimitResult(
            allowed=True,
            limit=limit,
            remaining=remaining,
            reset_unix=reset_unix,
        )

    async def aclose(self) -> None:
        if self._owned:
            await self._redis.aclose()


def build_mcp_rate_limiter(
    *,
    redis_url: str,
    default_rpm: int,
    org_overrides: dict[UUID, int],
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
