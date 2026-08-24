"""Thin async Redis store for embedding vectors (float32 bytes only)."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class RedisEmbeddingStore:
    """MGET / pipeline SET EX / PING / aclose over redis-asyncio."""

    def __init__(self, client: Redis) -> None:
        self._client = client

    @classmethod
    def from_url(cls, url: str, *, timeout_seconds: float) -> RedisEmbeddingStore:
        client = Redis.from_url(
            url,
            socket_connect_timeout=timeout_seconds,
            socket_timeout=timeout_seconds,
            decode_responses=False,
        )
        return cls(client)

    async def ping(self) -> None:
        await self._client.ping()

    async def mget(self, keys: Sequence[str]) -> list[bytes | None]:
        if not keys:
            return []
        values = await self._client.mget(list(keys))
        return list(values)

    async def set_many_ex(
        self,
        items: Sequence[tuple[str, bytes]],
        *,
        ttl_seconds: int,
    ) -> None:
        if not items:
            return
        pipe = self._client.pipeline(transaction=False)
        for key, value in items:
            pipe.set(key, value, ex=ttl_seconds)
        await pipe.execute()

    async def aclose(self) -> None:
        await self._client.aclose()
