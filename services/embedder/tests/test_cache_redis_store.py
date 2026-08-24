"""Unit tests for RedisEmbeddingStore edge paths."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.cache.redis_store import RedisEmbeddingStore


class TestRedisStoreEdges:
    async def test_mget_empty_keys_short_circuits(self) -> None:
        client = MagicMock()
        client.mget = AsyncMock()
        store = RedisEmbeddingStore(client)
        assert await store.mget([]) == []
        client.mget.assert_not_called()

    async def test_set_many_empty_items_short_circuits(self) -> None:
        client = MagicMock()
        client.pipeline = MagicMock()
        store = RedisEmbeddingStore(client)
        await store.set_many_ex([], ttl_seconds=10)
        client.pipeline.assert_not_called()

    async def test_from_url_and_ping_aclose(self) -> None:
        from redis.exceptions import RedisError

        store = RedisEmbeddingStore.from_url(
            "redis://127.0.0.1:1/0",
            timeout_seconds=0.05,
        )
        with pytest.raises((RedisError, OSError, TimeoutError)):
            await store.ping()
        await store.aclose()
