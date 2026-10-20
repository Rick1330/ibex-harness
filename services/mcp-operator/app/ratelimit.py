"""Org-scoped operator-gateway calendar-minute rate limiter.

Twin of ``services/mcp-memory/app/ratelimit.py`` (and ``packages/ratelimit/window.go``):
Lua INCR + EXPIRE-on-create (90s), key ``ratelimit:{org_id}:mcp_operator:{unix_minute}``.
Development may fail open; protected profiles fail closed with
``rate_limit_unavailable``.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from uuid import UUID

from mcp_gateway import RateLimitOutcome, RateLimitUnavailableError
from prometheus_client import Counter
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.dependency_metrics import REDIS_DURATION

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
    "ibex_mcp_operator_rate_limit_errors_total",
    "Operator gateway rate-limit Redis failures",
)
RATE_LIMIT_REJECTED = Counter(
    "ibex_mcp_operator_rate_limit_rejected_total",
    "Operator gateway tool calls rejected for exceeding org RPM",
)


class OperatorRateLimiter(ABC):
    @abstractmethod
    async def check(self, org_id: UUID) -> RateLimitOutcome:
        raise NotImplementedError


class NoopOperatorLimiter(OperatorRateLimiter):
    """Always allow — used when no Redis URL is configured."""

    def __init__(self, *, default_rpm: int = 120) -> None:
        self._default_rpm = max(1, default_rpm)

    async def check(self, org_id: UUID) -> RateLimitOutcome:
        del org_id
        now = int(time.time())
        reset = ((now // 60) + 1) * 60
        return RateLimitOutcome(
            allowed=True, limit=self._default_rpm, remaining=self._default_rpm, reset_unix=reset
        )


class RedisOperatorLimiter(OperatorRateLimiter):
    def __init__(
        self,
        redis: Redis,
        *,
        default_rpm: int = 120,
        org_overrides: dict[UUID, int] | None = None,
        owned: bool = True,
        fail_closed: bool = False,
    ) -> None:
        self._redis = redis
        self._default_rpm = max(1, default_rpm)
        self._org_overrides = org_overrides or {}
        self._owned = owned
        self._fail_closed = fail_closed
        self._script = self._redis.register_script(INCR_EXPIRE_LUA)

    def effective_limit(self, org_id: UUID) -> int:
        override = self._org_overrides.get(org_id)
        if override is not None and override > 0:
            return override
        return self._default_rpm

    @staticmethod
    def redis_key(org_id: UUID, *, unix_minute: int | None = None) -> str:
        minute = unix_minute if unix_minute is not None else int(time.time()) // 60
        return f"ratelimit:{org_id}:mcp_operator:{minute}"

    async def check(self, org_id: UUID) -> RateLimitOutcome:
        limit = self.effective_limit(org_id)
        now = int(time.time())
        unix_minute = now // 60
        reset_unix = (unix_minute + 1) * 60
        key = self.redis_key(org_id, unix_minute=unix_minute)
        started = time.perf_counter()
        try:
            count = int(await self._script(keys=[key], args=[KEY_TTL_SECONDS]))
        except (OSError, RedisError) as exc:
            RATE_LIMIT_ERRORS.inc()
            if self._fail_closed:
                raise RateLimitUnavailableError() from exc
            logger.warning(
                "mcp operator rate limit redis fail-open development exception org_id=%s error_class=%s",
                org_id,
                type(exc).__name__,
            )
            return RateLimitOutcome(
                allowed=True, limit=limit, remaining=limit, reset_unix=reset_unix
            )
        finally:
            REDIS_DURATION.observe(time.perf_counter() - started)
        if count > limit:
            RATE_LIMIT_REJECTED.inc()
            return RateLimitOutcome(allowed=False, limit=limit, remaining=0, reset_unix=reset_unix)
        remaining = max(0, limit - count)
        return RateLimitOutcome(
            allowed=True, limit=limit, remaining=remaining, reset_unix=reset_unix
        )

    async def aclose(self) -> None:
        if self._owned:
            await self._redis.aclose()


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
