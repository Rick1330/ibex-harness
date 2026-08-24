"""CachingEmbeddingBackend — Redis content-hash decorator over any backend."""

from __future__ import annotations

import logging
from uuid import UUID

import numpy as np
from numpy.typing import NDArray
from redis.exceptions import RedisError

from app.backends.base import EmbeddingBackend
from app.cache.context import embed_org_id
from app.cache.keys import cache_key_for_text
from app.cache.metrics import record_error, record_hit, record_miss
from app.cache.redis_store import RedisEmbeddingStore
from app.errors import MissingOrgContextError
from app.profiles import Profile
from app.validate import validate_embed_input

logger = logging.getLogger(__name__)

_FLOAT32_BYTES = 4
_REDIS_FAIL_OPEN = (RedisError, OSError, TimeoutError)

def _decode_vector(blob: bytes | None, *, dimensions: int) -> NDArray[np.float32] | None:
    if blob is None:
        return None
    expected = dimensions * _FLOAT32_BYTES
    if len(blob) != expected:
        return None
    return np.frombuffer(blob, dtype=np.float32).copy()


def _encode_vector(vec: NDArray[np.float32]) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


class CachingEmbeddingBackend(EmbeddingBackend):
    """Wraps an EmbeddingBackend with org-scoped Redis content-hash cache.

    ``name`` / ``model_id`` / ``dimensions`` / ``profile`` forward to the inner
    backend so JSON responses stay unchanged (not ``cached:openai``).
    """

    def __init__(
        self,
        inner: EmbeddingBackend,
        store: RedisEmbeddingStore,
        *,
        ttl_seconds: int,
    ) -> None:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be >= 1")
        self._inner = inner
        self._store = store
        self._ttl_seconds = ttl_seconds

    @property
    def inner(self) -> EmbeddingBackend:
        return self._inner

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    @property
    def dimensions(self) -> int:
        return self._inner.dimensions

    @property
    def profile(self) -> Profile:
        return self._inner.profile

    async def embed(self, texts: list[str]) -> NDArray[np.float32]:
        validate_embed_input(texts)
        org_id = embed_org_id.get()
        if org_id is None:
            raise MissingOrgContextError("org_id is required when embedding cache is enabled")
        return await self._embed_cached(texts, org_id)

    async def _embed_cached(
        self,
        texts: list[str],
        org_id: UUID,
    ) -> NDArray[np.float32]:
        keys = [
            cache_key_for_text(
                org_id=org_id,
                model_id=self._inner.model_id,
                dimensions=self._inner.dimensions,
                text=text,
            )
            for text in texts
        ]
        try:
            raw_values = await self._store.mget(keys)
        except _REDIS_FAIL_OPEN as exc:
            record_error("mget")
            logger.warning(
                "embedding cache mget fail-open error_class=%s",
                type(exc).__name__,
            )
            for _ in texts:
                record_miss(self._inner.name)
            return await self._inner.embed(texts)

        results: list[NDArray[np.float32] | None] = [None] * len(texts)
        miss_indices: list[int] = []
        for i, blob in enumerate(raw_values):
            decoded = _decode_vector(blob, dimensions=self._inner.dimensions)
            if decoded is not None:
                results[i] = decoded
                record_hit(self._inner.name)
            else:
                miss_indices.append(i)
                record_miss(self._inner.name)

        if miss_indices:
            await self._fill_misses(texts, keys, results, miss_indices)

        stacked = np.vstack([results[i] for i in range(len(texts))])  # type: ignore[misc]
        return stacked.astype(np.float32, copy=False)

    async def _fill_misses(
        self,
        texts: list[str],
        keys: list[str],
        results: list[NDArray[np.float32] | None],
        miss_indices: list[int],
    ) -> None:
        miss_texts = [texts[i] for i in miss_indices]
        unique_texts: list[str] = []
        text_to_unique: dict[str, int] = {}
        for text in miss_texts:
            if text not in text_to_unique:
                text_to_unique[text] = len(unique_texts)
                unique_texts.append(text)

        unique_vectors = await self._inner.embed(unique_texts)
        to_store: list[tuple[str, bytes]] = []
        for text_idx in miss_indices:
            unique_idx = text_to_unique[texts[text_idx]]
            vec = unique_vectors[unique_idx]
            results[text_idx] = vec
            to_store.append((keys[text_idx], _encode_vector(vec)))

        try:
            await self._store.set_many_ex(to_store, ttl_seconds=self._ttl_seconds)
        except _REDIS_FAIL_OPEN as exc:
            record_error("set")
            logger.warning(
                "embedding cache set fail-open error_class=%s",
                type(exc).__name__,
            )

    async def aclose(self) -> None:
        await self._store.aclose()
        inner = self._inner
        if hasattr(inner, "aclose"):
            await inner.aclose()  # type: ignore[misc]

    async def ping(self) -> None:
        """Startup readiness check against Redis."""
        await self._store.ping()
