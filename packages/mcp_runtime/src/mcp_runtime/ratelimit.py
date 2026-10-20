"""Org-scoped calendar-minute rate limiting shared by MCP services."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from typing import Any
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


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_unix: int


@dataclass(frozen=True, slots=True)
class RateLimitMetrics:
    errors: Counter
    rejected: Counter
    duration: Callable[[float], None] | None = None


def build_rate_limit_metrics(*, prefix: str, service: str) -> RateLimitMetrics:
    return RateLimitMetrics(
        errors=Counter(
            f"{prefix}_rate_limit_errors_total",
            f"{service} rate-limit Redis failures",
        ),
        rejected=Counter(
            f"{prefix}_rate_limit_rejected_total",
            f"{service} calls rejected for exceeding org RPM",
        ),
    )


def redis_key(scope: str, org_id: UUID, *, unix_minute: int | None = None) -> str:
    minute = unix_minute if unix_minute is not None else int(time.time()) // 60
    return f"ratelimit:{org_id}:{scope}:{minute}"


class CalendarMinuteRateLimiter[ResultT](ABC):
    @abstractmethod
    async def check(self, org_id: UUID) -> ResultT:
        raise NotImplementedError


class NoopRateLimiter[ResultT](CalendarMinuteRateLimiter[ResultT]):
    """Always allow — used when no Redis URL is configured."""

    def __init__(
        self,
        *,
        default_rpm: int = 120,
        result_factory: Callable[..., ResultT] = RateLimitResult,
    ) -> None:
        self._default_rpm = max(1, default_rpm)
        self._result_factory = result_factory

    async def check(self, org_id: UUID) -> ResultT:
        del org_id
        now = int(time.time())
        reset = ((now // 60) + 1) * 60
        return self._result_factory(
            allowed=True,
            limit=self._default_rpm,
            remaining=self._default_rpm,
            reset_unix=reset,
        )


class RedisCalendarMinuteRateLimiter[ResultT](CalendarMinuteRateLimiter[ResultT]):
    def __init__(
        self,
        redis: Redis,
        *,
        key_scope: str,
        default_rpm: int = 120,
        org_overrides: dict[UUID, int] | None = None,
        owned: bool = True,
        fail_closed: bool = False,
        unavailable_error: type[Exception] = RuntimeError,
        result_factory: Callable[..., ResultT] = RateLimitResult,
        metrics: RateLimitMetrics | None = None,
        span: Callable[[str], AbstractContextManager[Any]] = lambda _name: nullcontext(),
        log_label: str = "mcp",
    ) -> None:
        self._redis = redis
        self._key_scope = key_scope
        self._default_rpm = max(1, default_rpm)
        self._org_overrides = org_overrides or {}
        self._owned = owned
        self._fail_closed = fail_closed
        self._unavailable_error = unavailable_error
        self._result_factory = result_factory
        self._metrics = metrics
        self._span = span
        self._log_label = log_label
        self._script = self._redis.register_script(INCR_EXPIRE_LUA)

    def effective_limit(self, org_id: UUID) -> int:
        override = self._org_overrides.get(org_id)
        if override is not None and override > 0:
            return override
        return self._default_rpm

    def redis_key(self, org_id: UUID, *, unix_minute: int | None = None) -> str:
        return redis_key(self._key_scope, org_id, unix_minute=unix_minute)

    async def check(self, org_id: UUID) -> ResultT:
        limit = self.effective_limit(org_id)
        now = int(time.time())
        unix_minute = now // 60
        reset_unix = (unix_minute + 1) * 60
        key = self.redis_key(org_id, unix_minute=unix_minute)
        started = time.perf_counter()
        try:
            with self._span("redis.rate_limit"):
                count = int(await self._script(keys=[key], args=[KEY_TTL_SECONDS]))
        except (OSError, RedisError) as exc:
            self._record_error()
            if self._fail_closed:
                raise self._unavailable_error() from exc
            logger.warning(
                "%s rate limit redis fail-open development exception org_id=%s error_class=%s",
                self._log_label,
                org_id,
                type(exc).__name__,
            )
            return self._result_factory(
                allowed=True,
                limit=limit,
                remaining=limit,
                reset_unix=reset_unix,
            )
        finally:
            if self._metrics is not None and self._metrics.duration is not None:
                self._metrics.duration(time.perf_counter() - started)
        remaining = max(0, limit - count)
        if count > limit:
            self._record_rejected()
            return self._result_factory(
                allowed=False,
                limit=limit,
                remaining=0,
                reset_unix=reset_unix,
            )
        return self._result_factory(
            allowed=True,
            limit=limit,
            remaining=remaining,
            reset_unix=reset_unix,
        )

    def _record_error(self) -> None:
        if self._metrics is not None:
            self._metrics.errors.inc()

    def _record_rejected(self) -> None:
        if self._metrics is not None:
            self._metrics.rejected.inc()

    async def aclose(self) -> None:
        if self._owned:
            await self._redis.aclose()
