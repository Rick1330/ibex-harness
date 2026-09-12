"""Best-effort Redis publish for model-policy invalidation (m4.C.2)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Protocol

logger = logging.getLogger(__name__)

_CHANNEL_PREFIX = "model_policy_updates:"
_EVENT_VERSION = 1
_REDIS_SOCKET_TIMEOUT_SECONDS = 1.0


class ModelPolicyPublisher(Protocol):
    async def publish_policy_update(self, org_id: str) -> None: ...


class NoopModelPolicyPublisher:
    async def publish_policy_update(self, org_id: str) -> None:
        del org_id
        await asyncio.sleep(0)


class RecordingModelPolicyPublisher:
    def __init__(self) -> None:
        self.published: list[str] = []

    async def publish_policy_update(self, org_id: str) -> None:
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


class RedisModelPolicyPublisher:
    """PUBLISH {v, org_id} to model_policy_updates:{org_id}."""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = _redis_from_url(self._redis_url)
        return self._client

    async def publish_policy_update(self, org_id: str) -> None:
        client = self._get_client()
        channel = f"{_CHANNEL_PREFIX}{org_id}"
        payload = json.dumps({"v": _EVENT_VERSION, "org_id": org_id})
        await client.publish(channel, payload)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
