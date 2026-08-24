"""Unit tests for CachingEmbeddingBackend (mock Redis store)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import numpy as np
import pytest

from app.backends.stub import StubBackend
from app.cache.backend import CachingEmbeddingBackend
from app.cache.context import reset_embed_org_id, set_embed_org_id
from app.cache.keys import cache_key_for_text
from app.cache.metrics import CACHE_ERRORS, CACHE_REQUESTS
from app.errors import MissingOrgContextError

_ORG = UUID("11111111-1111-1111-1111-111111111111")
_ORG_B = UUID("22222222-2222-2222-2222-222222222222")


def _l2(n: int, dim: int = 8) -> np.ndarray:
    rng = np.random.default_rng(0)
    raw = rng.standard_normal((n, dim)).astype(np.float32)
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    return (raw / norms).astype(np.float32)


def _counting_inner(dim: int = 8) -> MagicMock:
    inner = MagicMock()
    inner.name = "stub"
    inner.model_id = "all-MiniLM-L6-v2"
    inner.dimensions = dim
    inner.profile = "cpu"
    inner.embed_calls = []

    async def _embed(texts: list[str]) -> np.ndarray:
        inner.embed_calls.append(list(texts))
        return _l2(len(texts), dim)

    inner.embed = AsyncMock(side_effect=_embed)
    inner.aclose = AsyncMock()
    return inner


@pytest.fixture
def org_ctx():
    token = set_embed_org_id(_ORG)
    yield _ORG
    reset_embed_org_id(token)


class TestCachingBackendUnit:
    async def test_miss_then_hit_skips_inner(self, org_ctx: UUID) -> None:
        store: dict[str, bytes] = {}

        mock_store = MagicMock()
        mock_store.mget = AsyncMock(
            side_effect=lambda keys: [store.get(k) for k in keys]
        )

        async def _set_many(items, *, ttl_seconds: int) -> None:
            for key, value in items:
                store[key] = value

        mock_store.set_many_ex = AsyncMock(side_effect=_set_many)
        mock_store.aclose = AsyncMock()

        inner = _counting_inner()
        cached = CachingEmbeddingBackend(inner, mock_store, ttl_seconds=60)

        first = await cached.embed(["hello"])
        second = await cached.embed(["hello"])

        assert first.shape == (1, 8)
        np.testing.assert_array_equal(first, second)
        assert len(inner.embed_calls) == 1
        assert mock_store.set_many_ex.await_count == 1

    async def test_partial_batch_mixed_hit_miss(self, org_ctx: UUID) -> None:
        inner = _counting_inner()
        store: dict[str, bytes] = {}
        mock_store = MagicMock()
        mock_store.mget = AsyncMock(
            side_effect=lambda keys: [store.get(k) for k in keys]
        )

        async def _set_many(items, *, ttl_seconds: int) -> None:
            for key, value in items:
                store[key] = value

        mock_store.set_many_ex = AsyncMock(side_effect=_set_many)
        cached = CachingEmbeddingBackend(inner, mock_store, ttl_seconds=60)

        await cached.embed(["a"])
        result = await cached.embed(["a", "b", "a"])
        assert result.shape == (3, 8)
        # Second call: only unique miss "b" should hit inner once.
        assert inner.embed_calls[-1] == ["b"]

    async def test_duplicate_miss_texts_embedded_once(self, org_ctx: UUID) -> None:
        inner = _counting_inner()
        mock_store = MagicMock()
        mock_store.mget = AsyncMock(return_value=[None, None, None])
        mock_store.set_many_ex = AsyncMock()
        cached = CachingEmbeddingBackend(inner, mock_store, ttl_seconds=60)

        result = await cached.embed(["x", "y", "x"])
        assert result.shape == (3, 8)
        assert inner.embed_calls == [["x", "y"]]
        # Three SET entries (one per batch slot), even for duplicate text.
        written = mock_store.set_many_ex.await_args.args[0]
        assert len(written) == 3

    async def test_corrupt_blob_counts_as_miss(self, org_ctx: UUID) -> None:
        inner = _counting_inner(dim=8)
        key = cache_key_for_text(
            org_id=_ORG,
            model_id=inner.model_id,
            dimensions=8,
            text="z",
        )
        mock_store = MagicMock()
        mock_store.mget = AsyncMock(return_value=[b"short"])
        mock_store.set_many_ex = AsyncMock()
        cached = CachingEmbeddingBackend(inner, mock_store, ttl_seconds=60)

        await cached.embed(["z"])
        assert inner.embed_calls == [["z"]]
        assert mock_store.set_many_ex.await_count == 1
        assert key  # key format exercised

    async def test_mget_error_fail_open(self, org_ctx: UUID) -> None:
        inner = _counting_inner()
        mock_store = MagicMock()
        mock_store.mget = AsyncMock(side_effect=ConnectionError("down"))
        mock_store.set_many_ex = AsyncMock()
        cached = CachingEmbeddingBackend(inner, mock_store, ttl_seconds=60)

        before = CACHE_ERRORS.labels(op="mget")._value.get()
        result = await cached.embed(["hello"])
        assert result.shape == (1, 8)
        assert inner.embed_calls == [["hello"]]
        assert mock_store.set_many_ex.await_count == 0
        assert CACHE_ERRORS.labels(op="mget")._value.get() == before + 1

    async def test_set_error_still_returns_vectors(self, org_ctx: UUID) -> None:
        from redis.exceptions import TimeoutError as RedisTimeoutError

        inner = _counting_inner()
        mock_store = MagicMock()
        mock_store.mget = AsyncMock(return_value=[None])
        mock_store.set_many_ex = AsyncMock(side_effect=RedisTimeoutError("slow"))
        cached = CachingEmbeddingBackend(inner, mock_store, ttl_seconds=60)

        before = CACHE_ERRORS.labels(op="set")._value.get()
        result = await cached.embed(["hello"])
        assert result.shape == (1, 8)
        assert CACHE_ERRORS.labels(op="set")._value.get() == before + 1

    async def test_missing_org_context_raises(self) -> None:
        inner = _counting_inner()
        mock_store = MagicMock()
        cached = CachingEmbeddingBackend(inner, mock_store, ttl_seconds=60)
        with pytest.raises(MissingOrgContextError):
            await cached.embed(["hello"])
        assert inner.embed.await_count == 0

    async def test_name_forwards_inner_not_cached_prefix(self, org_ctx: UUID) -> None:
        inner = StubBackend.for_profile("cpu")
        mock_store = MagicMock()
        mock_store.mget = AsyncMock(return_value=[None])
        mock_store.set_many_ex = AsyncMock()
        cached = CachingEmbeddingBackend(inner, mock_store, ttl_seconds=60)
        assert cached.name == "stub"
        assert cached.model_id == inner.model_id
        assert cached.dimensions == inner.dimensions
        assert cached.profile == "cpu"

    async def test_metrics_hit_miss_per_text(self, org_ctx: UUID) -> None:
        store: dict[str, bytes] = {}
        mock_store = MagicMock()
        mock_store.mget = AsyncMock(
            side_effect=lambda keys: [store.get(k) for k in keys]
        )

        async def _set_many(items, *, ttl_seconds: int) -> None:
            for key, value in items:
                store[key] = value

        mock_store.set_many_ex = AsyncMock(side_effect=_set_many)
        inner = _counting_inner()
        cached = CachingEmbeddingBackend(inner, mock_store, ttl_seconds=60)

        hits_before = CACHE_REQUESTS.labels(backend="stub", result="hit")._value.get()
        misses_before = CACHE_REQUESTS.labels(backend="stub", result="miss")._value.get()

        await cached.embed(["a"])
        await cached.embed(["a", "b"])

        assert CACHE_REQUESTS.labels(backend="stub", result="miss")._value.get() == (
            misses_before + 2
        )  # a then b
        assert CACHE_REQUESTS.labels(backend="stub", result="hit")._value.get() == (
            hits_before + 1
        )  # second a

    async def test_cross_tenant_no_shared_hit(self) -> None:
        store: dict[str, bytes] = {}
        mock_store = MagicMock()
        mock_store.mget = AsyncMock(
            side_effect=lambda keys: [store.get(k) for k in keys]
        )

        async def _set_many(items, *, ttl_seconds: int) -> None:
            for key, value in items:
                store[key] = value

        mock_store.set_many_ex = AsyncMock(side_effect=_set_many)
        inner = _counting_inner()
        cached = CachingEmbeddingBackend(inner, mock_store, ttl_seconds=60)

        token_a = set_embed_org_id(_ORG)
        try:
            await cached.embed(["shared"])
        finally:
            reset_embed_org_id(token_a)

        token_b = set_embed_org_id(_ORG_B)
        try:
            await cached.embed(["shared"])
        finally:
            reset_embed_org_id(token_b)

        assert len(inner.embed_calls) == 2
        assert len(store) == 2

    async def test_aclose_closes_store_and_inner(self, org_ctx: UUID) -> None:
        inner = _counting_inner()
        mock_store = MagicMock()
        mock_store.aclose = AsyncMock()
        cached = CachingEmbeddingBackend(inner, mock_store, ttl_seconds=60)
        await cached.aclose()
        mock_store.aclose.assert_awaited_once()
        inner.aclose.assert_awaited_once()

    async def test_never_caches_inner_errors(self, org_ctx: UUID) -> None:
        inner = _counting_inner()
        inner.embed = AsyncMock(side_effect=RuntimeError("boom"))
        mock_store = MagicMock()
        mock_store.mget = AsyncMock(return_value=[None])
        mock_store.set_many_ex = AsyncMock()
        cached = CachingEmbeddingBackend(inner, mock_store, ttl_seconds=60)
        with pytest.raises(RuntimeError, match="boom"):
            await cached.embed(["hello"])
        assert mock_store.set_many_ex.await_count == 0
