"""Unit tests for CachingEmbeddingBackend (in-memory mock Redis store)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import numpy as np
import pytest
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.backends.stub import StubBackend
from app.cache.backend import CachingEmbeddingBackend
from app.cache.context import org_context
from app.cache.metrics import CACHE_ERRORS, CACHE_REQUESTS
from app.cache.wire import encode_vector
from app.errors import MissingOrgContextError

_ORG = UUID("11111111-1111-1111-1111-111111111111")
_ORG_B = UUID("22222222-2222-2222-2222-222222222222")


def _l2_for_text(text: str, dim: int = 8) -> np.ndarray:
    """Deterministic unit vector unique per text."""
    seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
    rng = np.random.default_rng(seed)
    raw = rng.standard_normal(dim).astype(np.float32)
    return (raw / np.linalg.norm(raw)).astype(np.float32)


def _counting_inner(dim: int = 8) -> MagicMock:
    inner = MagicMock()
    inner.name = "stub"
    inner.model_id = "all-MiniLM-L6-v2"
    inner.dimensions = dim
    inner.profile = "cpu"
    calls: list[list[str]] = []
    inner.embed_calls = calls

    async def _embed(texts: list[str]) -> np.ndarray:
        calls.append(list(texts))
        return np.vstack([_l2_for_text(t, dim) for t in texts]).astype(np.float32)

    inner.embed = AsyncMock(side_effect=_embed)
    inner.aclose = AsyncMock()
    return inner


@dataclass
class _MockCache:
    data: dict[str, bytes]
    store: MagicMock
    inner: MagicMock
    cached: CachingEmbeddingBackend


def _mock_cache(*, dim: int = 8, prefill: dict[str, bytes] | None = None) -> _MockCache:
    data: dict[str, bytes] = dict(prefill or {})
    store = MagicMock()
    store.mget = AsyncMock(side_effect=lambda keys: [data.get(k) for k in keys])

    async def _set_many(items, *, ttl_seconds: int) -> None:
        for key, value in items:
            data[key] = value

    store.set_many_ex = AsyncMock(side_effect=_set_many)
    store.aclose = AsyncMock()
    inner = _counting_inner(dim)
    return _MockCache(
        data=data,
        store=store,
        inner=inner,
        cached=CachingEmbeddingBackend(inner, store, ttl_seconds=60),
    )


@pytest.fixture
def org_ctx():
    with org_context(_ORG) as oid:
        yield oid


class TestCachingBackendUnit:
    async def test_miss_then_hit_skips_inner(self, org_ctx: UUID) -> None:
        env = _mock_cache()
        first = await env.cached.embed(["hello"])
        second = await env.cached.embed(["hello"])
        np.testing.assert_array_equal(first, second)
        assert len(env.inner.embed_calls) == 1
        assert env.store.set_many_ex.await_count == 1

    async def test_partial_batch_preserves_order(self, org_ctx: UUID) -> None:
        env = _mock_cache()
        await env.cached.embed(["a"])
        result = await env.cached.embed(["a", "b", "a"])
        assert env.inner.embed_calls[-1] == ["b"]
        np.testing.assert_array_equal(result[0], _l2_for_text("a"))
        np.testing.assert_array_equal(result[1], _l2_for_text("b"))
        np.testing.assert_array_equal(result[2], result[0])
        assert not np.allclose(result[0], result[1])

    async def test_duplicate_miss_texts_embedded_once(self, org_ctx: UUID) -> None:
        env = _mock_cache()
        env.store.mget = AsyncMock(return_value=[None, None, None])
        result = await env.cached.embed(["x", "y", "x"])
        assert env.inner.embed_calls == [["x", "y"]]
        np.testing.assert_array_equal(result[0], result[2])
        np.testing.assert_array_equal(result[0], _l2_for_text("x"))
        # One SET per unique digest (x and y), not three.
        written = env.store.set_many_ex.await_args.args[0]
        assert len(written) == 2

    @pytest.mark.parametrize(
        ("blob", "text"),
        [
            (b"short", "z"),
            (encode_vector(np.full(8, np.nan, dtype=np.float32)), "bad"),
            (encode_vector(np.ones(8, dtype=np.float32)), "unnorm"),
        ],
        ids=["trunc", "nan", "non_unit_l2"],
    )
    async def test_invalid_blob_is_miss_and_overwritten(
        self,
        org_ctx: UUID,
        blob: bytes,
        text: str,
    ) -> None:
        env = _mock_cache()
        env.store.mget = AsyncMock(return_value=[blob])
        result = await env.cached.embed([text])
        assert env.inner.embed_calls == [[text]]
        assert np.all(np.isfinite(result))
        assert np.allclose(np.linalg.norm(result[0]), 1.0, atol=1e-5)
        assert env.store.set_many_ex.await_count == 1

    async def test_mget_error_fail_open(self, org_ctx: UUID) -> None:
        env = _mock_cache()
        env.store.mget = AsyncMock(side_effect=ConnectionError("down"))
        before = CACHE_ERRORS.labels(op="mget")._value.get()
        result = await env.cached.embed(["hello"])
        assert result.shape == (1, 8)
        assert env.inner.embed_calls == [["hello"]]
        assert env.store.set_many_ex.await_count == 0
        assert CACHE_ERRORS.labels(op="mget")._value.get() == before + 1

    async def test_set_error_still_returns_vectors(self, org_ctx: UUID) -> None:
        env = _mock_cache()
        env.store.mget = AsyncMock(return_value=[None])
        env.store.set_many_ex = AsyncMock(side_effect=RedisTimeoutError("slow"))
        before = CACHE_ERRORS.labels(op="set")._value.get()
        result = await env.cached.embed(["hello"])
        assert result.shape == (1, 8)
        assert CACHE_ERRORS.labels(op="set")._value.get() == before + 1

    async def test_missing_org_context_raises(self) -> None:
        env = _mock_cache()
        with pytest.raises(MissingOrgContextError):
            await env.cached.embed(["hello"])
        assert env.inner.embed.await_count == 0

    async def test_identity_forwards_inner(self, org_ctx: UUID) -> None:
        inner = StubBackend.for_profile("cpu")
        store = MagicMock()
        store.mget = AsyncMock(return_value=[None])
        store.set_many_ex = AsyncMock()
        cached = CachingEmbeddingBackend(inner, store, ttl_seconds=60)
        assert cached.name == "stub"
        assert cached.model_id == inner.model_id
        assert cached.dimensions == inner.dimensions
        assert cached.profile == "cpu"

    async def test_metrics_hit_miss_per_text(self, org_ctx: UUID) -> None:
        env = _mock_cache()
        hits_before = CACHE_REQUESTS.labels(backend="stub", result="hit")._value.get()
        misses_before = CACHE_REQUESTS.labels(backend="stub", result="miss")._value.get()
        await env.cached.embed(["a"])
        await env.cached.embed(["a", "b"])
        assert CACHE_REQUESTS.labels(backend="stub", result="miss")._value.get() == (
            misses_before + 2
        )
        assert CACHE_REQUESTS.labels(backend="stub", result="hit")._value.get() == (
            hits_before + 1
        )

    async def test_cross_tenant_no_shared_hit(self) -> None:
        env = _mock_cache()
        with org_context(_ORG):
            await env.cached.embed(["shared"])
        with org_context(_ORG_B):
            await env.cached.embed(["shared"])
        assert len(env.inner.embed_calls) == 2
        assert len(env.data) == 2

    async def test_rejects_non_positive_ttl(self) -> None:
        inner = _counting_inner()
        store = MagicMock()
        with pytest.raises(ValueError, match="ttl_seconds"):
            CachingEmbeddingBackend(inner, store, ttl_seconds=0)

    async def test_aclose_closes_store_and_inner(self) -> None:
        env = _mock_cache()
        await env.cached.aclose()
        env.store.aclose.assert_awaited_once()
        env.inner.aclose.assert_awaited_once()

    async def test_aclose_closes_inner_when_store_raises(self) -> None:
        env = _mock_cache()
        env.store.aclose = AsyncMock(side_effect=ConnectionError("redis gone"))
        with pytest.raises(ConnectionError, match="redis gone"):
            await env.cached.aclose()
        env.inner.aclose.assert_awaited_once()

    async def test_never_caches_inner_errors(self, org_ctx: UUID) -> None:
        env = _mock_cache()
        env.inner.embed = AsyncMock(side_effect=RuntimeError("boom"))
        env.store.mget = AsyncMock(return_value=[None])
        with pytest.raises(RuntimeError, match="boom"):
            await env.cached.embed(["hello"])
        assert env.store.set_many_ex.await_count == 0
