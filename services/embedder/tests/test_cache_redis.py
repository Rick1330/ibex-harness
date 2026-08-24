"""Real Redis integration tests for the embedding content-hash cache."""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import numpy as np
import pytest
import redis as redis_sync
from redis.exceptions import RedisError

from app.cache.backend import CachingEmbeddingBackend
from app.cache.context import org_context
from app.cache.keys import cache_key_for_text
from app.cache.redis_store import RedisEmbeddingStore

pytestmark = pytest.mark.redis

_ORG_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_ORG_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")


@pytest.fixture(scope="module")
def require_redis() -> str:
    client = redis_sync.Redis.from_url(
        _REDIS_URL,
        socket_connect_timeout=0.2,
        socket_timeout=0.2,
    )
    try:
        client.ping()
    except (RedisError, OSError, TimeoutError):
        pytest.skip(f"Redis not available at {_REDIS_URL}")
    finally:
        client.close()
    return _REDIS_URL


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _l2_for_text(text: str, dim: int = 8) -> np.ndarray:
    seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
    rng = np.random.default_rng(seed)
    raw = rng.standard_normal(dim).astype(np.float32)
    return (raw / np.linalg.norm(raw)).astype(np.float32)


def _inner(dim: int = 8) -> MagicMock:
    inner = MagicMock()
    inner.name = "stub"
    inner.model_id = "test-model"
    inner.dimensions = dim
    inner.profile = "cpu"
    calls: list[list[str]] = []
    inner.embed_calls = calls

    async def _embed(texts: list[str]) -> np.ndarray:
        calls.append(list(texts))
        rows = [_l2_for_text(t, dim) for t in texts]
        return np.vstack(rows).astype(np.float32)

    inner.embed = AsyncMock(side_effect=_embed)
    inner.aclose = AsyncMock()
    return inner


@pytest.fixture
async def store(require_redis: str):
    s = RedisEmbeddingStore.from_url(require_redis, timeout_seconds=0.5)
    yield s
    await s.aclose()


async def _embed_under_org(
    cached: CachingEmbeddingBackend,
    org_id: UUID,
    texts: list[str],
) -> np.ndarray:
    with org_context(org_id):
        return await cached.embed(texts)


class TestRedisIntegration:
    async def test_pipeline_write_and_hit(self, store: RedisEmbeddingStore) -> None:
        text = _unique("redis-hit-text")
        inner = _inner()
        cached = CachingEmbeddingBackend(inner, store, ttl_seconds=30)
        first = await _embed_under_org(cached, _ORG_A, [text])
        second = await _embed_under_org(cached, _ORG_A, [text])

        np.testing.assert_array_equal(first, second)
        assert len(inner.embed_calls) == 1

        key = cache_key_for_text(
            org_id=_ORG_A,
            model_id="test-model",
            dimensions=8,
            text=text,
        )
        values = await store.mget([key])
        assert values[0] is not None
        assert len(values[0]) == 8 * 4

    async def test_cross_tenant_isolation(self, store: RedisEmbeddingStore) -> None:
        text = _unique("tenant-shared")
        inner = _inner()
        cached = CachingEmbeddingBackend(inner, store, ttl_seconds=30)
        await _embed_under_org(cached, _ORG_A, [text])
        await _embed_under_org(cached, _ORG_B, [text])
        assert len(inner.embed_calls) == 2

    async def test_ttl_expiry(self, store: RedisEmbeddingStore) -> None:
        text = _unique("ttl-expire")
        inner = _inner()
        cached = CachingEmbeddingBackend(inner, store, ttl_seconds=1)
        await _embed_under_org(cached, _ORG_A, [text])
        assert len(inner.embed_calls) == 1
        await asyncio.sleep(1.2)
        await _embed_under_org(cached, _ORG_A, [text])
        assert len(inner.embed_calls) == 2

    async def test_fail_open_closed_port(self) -> None:
        bad = RedisEmbeddingStore.from_url(
            "redis://127.0.0.1:1/0",
            timeout_seconds=0.05,
        )
        inner = _inner()
        cached = CachingEmbeddingBackend(inner, bad, ttl_seconds=30)
        try:
            result = await _embed_under_org(cached, _ORG_A, [_unique("fail-open")])
        finally:
            await bad.aclose()
        assert result.shape == (1, 8)
        assert len(inner.embed_calls) == 1

    async def test_new_store_still_hits(self, require_redis: str) -> None:
        """Simulate process restart: new client still reads prior SETs."""
        text = _unique("restart-hit")
        inner1 = _inner()
        store1 = RedisEmbeddingStore.from_url(require_redis, timeout_seconds=0.5)
        cached1 = CachingEmbeddingBackend(inner1, store1, ttl_seconds=60)
        try:
            await _embed_under_org(cached1, _ORG_A, [text])
        finally:
            await store1.aclose()

        inner2 = _inner()
        store2 = RedisEmbeddingStore.from_url(require_redis, timeout_seconds=0.5)
        cached2 = CachingEmbeddingBackend(inner2, store2, ttl_seconds=60)
        try:
            await _embed_under_org(cached2, _ORG_A, [text])
        finally:
            await store2.aclose()

        assert inner2.embed_calls == []
