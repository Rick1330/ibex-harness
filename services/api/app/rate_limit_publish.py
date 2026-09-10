"""Best-effort Redis publish for rate-limit config invalidation (m4.B.2)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Protocol

logger = logging.getLogger(__name__)

_CHANNEL_PREFIX = "ratelimit_config_updates:"
_EVENT_VERSION = 1
_REDIS_SOCKET_TIMEOUT_SECONDS = 1.0


class RateLimitConfigPublisher(Protocol):
    async def publish_config_update(self, org_id: str) -> None: ...


class NoopRateLimitConfigPublisher:
    async def publish_config_update(self, org_id: str) -> None:
        del org_id
        await asyncio.sleep(0)


class RecordingRateLimitConfigPublisher:
    def __init__(self) -> None:
        self.published: list[str] = []

    async def publish_config_update(self, org_id: str) -> None:
        await asyncio.sleep(0)
        self.published.append(org_id)


def _redis_from_url(redis_url: str):
    from redis.asyncio import Redis

    return Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=_REDIS_SOCKET_TIMEOUT_SECONDS,
        socket_timeout=_REDIS_SOCKET_TIMEOUT_SECONDS,
    )


class RedisRateLimitConfigPublisher:
    """PUBLISH {v, org_id} to ratelimit_config_updates:{org_id}."""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = _redis_from_url(self._redis_url)
        return self._client

    async def publish_config_update(self, org_id: str) -> None:
        client = self._get_client()
        channel = f"{_CHANNEL_PREFIX}{org_id}"
        payload = json.dumps({"v": _EVENT_VERSION, "org_id": org_id})
        await client.publish(channel, payload)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class RedisRateLimitCounter:
    """Read live org RPM counter; returns 0 when Redis is unavailable."""

    def __init__(self, redis_url: str | None) -> None:
        self._redis_url = redis_url
        self._client = None

    def _get_client(self):
        if not self._redis_url:
            return None
        if self._client is None:
            self._client = _redis_from_url(self._redis_url)
        return self._client

    async def org_current_minute_requests(self, org_id: str) -> int:
        client = self._get_client()
        if client is None:
            return 0
        import time

        unix_minute = int(time.time()) // 60
        key = f"ratelimit:{org_id}:rpm:{unix_minute}"
        try:
            raw = await client.get(key)
        except Exception as exc:  # noqa: BLE001 — fail soft for live counters
            logger.warning(
                "rate-limit counter GET failed org_id=%s error_class=%s",
                org_id,
                type(exc).__name__,
            )
            return 0
        if raw is None:
            return 0
        try:
            return max(int(raw), 0)
        except ValueError:
            return 0

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
