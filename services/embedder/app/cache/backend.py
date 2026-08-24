"""CachingEmbeddingBackend — org-scoped Redis content-hash decorator."""

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
from app.cache.wire import decode_vector, encode_vector, is_contract_vector
from app.errors import MissingOrgContextError
from app.profiles import Profile
from app.validate import validate_embed_input

logger = logging.getLogger(__name__)

_REDIS_FAIL_OPEN = (RedisError, OSError, TimeoutError)


def _dedupe_preserve_order(texts: list[str]) -> tuple[list[str], list[int]]:
    """Return unique texts and a map from each input index → unique index."""
    index: dict[str, int] = {}
    unique: list[str] = []
    mapping: list[int] = []
    for text in texts:
        pos = index.get(text)
        if pos is None:
            pos = len(unique)
            index[text] = pos
            unique.append(text)
        mapping.append(pos)
    return unique, mapping


class CachingEmbeddingBackend(EmbeddingBackend):
    """Wrap any EmbeddingBackend with a content-addressed Redis cache.

    Geometry and identity (``name`` / ``model_id`` / ``dimensions`` / ``profile``)
    forward to the inner backend so JSON responses stay unchanged — never
    ``cached:openai``. Org scope comes from the ``embed_org_id`` ContextVar.
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
            raise MissingOrgContextError(
                "org_id is required when embedding cache is enabled"
            )
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
        blobs = await self._mget_fail_open(keys, batch_size=len(texts))
        if blobs is None:
            return await self._inner.embed(texts)

        rows, misses = self._split_hits_and_misses(blobs)
        if misses:
            await self._resolve_misses(texts, keys, rows, misses)
        return self._assemble(rows)

    async def _mget_fail_open(
        self,
        keys: list[str],
        *,
        batch_size: int,
    ) -> list[bytes | None] | None:
        try:
            return await self._store.mget(keys)
        except _REDIS_FAIL_OPEN as exc:
            record_error("mget")
            logger.warning(
                "embedding cache mget fail-open error_class=%s",
                type(exc).__name__,
            )
            backend = self._inner.name
            for _ in range(batch_size):
                record_miss(backend)
            return None

    def _split_hits_and_misses(
        self,
        blobs: list[bytes | None],
    ) -> tuple[list[NDArray[np.float32] | None], list[int]]:
        dim = self._inner.dimensions
        backend = self._inner.name
        rows: list[NDArray[np.float32] | None] = [None] * len(blobs)
        misses: list[int] = []
        for i, blob in enumerate(blobs):
            vec = decode_vector(blob, dimensions=dim)
            if vec is not None and is_contract_vector(vec, dimensions=dim):
                rows[i] = vec
                record_hit(backend)
            else:
                misses.append(i)
                record_miss(backend)
        return rows, misses

    async def _resolve_misses(
        self,
        texts: list[str],
        keys: list[str],
        rows: list[NDArray[np.float32] | None],
        misses: list[int],
    ) -> None:
        miss_texts = [texts[i] for i in misses]
        unique_texts, unique_of = _dedupe_preserve_order(miss_texts)
        vectors = await self._inner.embed(unique_texts)

        # One SET per unique key — duplicate texts in a batch share a digest.
        pending: dict[str, bytes] = {}
        for slot, text_idx in enumerate(misses):
            vec = vectors[unique_of[slot]]
            rows[text_idx] = vec
            pending[keys[text_idx]] = encode_vector(vec)

        try:
            await self._store.set_many_ex(
                list(pending.items()),
                ttl_seconds=self._ttl_seconds,
            )
        except _REDIS_FAIL_OPEN as exc:
            record_error("set")
            logger.warning(
                "embedding cache set fail-open error_class=%s",
                type(exc).__name__,
            )

    @staticmethod
    def _assemble(rows: list[NDArray[np.float32] | None]) -> NDArray[np.float32]:
        if any(row is None for row in rows):
            raise RuntimeError("embedding cache left unresolved miss slots")
        filled: list[NDArray[np.float32]] = rows  # type: ignore[assignment]
        return np.ascontiguousarray(np.vstack(filled), dtype=np.float32)

    async def aclose(self) -> None:
        await self._store.aclose()
        aclose = getattr(self._inner, "aclose", None)
        if aclose is not None:
            await aclose()

    async def ping(self) -> None:
        """Startup readiness check against Redis."""
        await self._store.ping()
