"""Redis object cache + hot sorted-set writes (m3.C.5 / ADR-0057)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.cache.hot_score import compute_hot_cache_score
from app.cache.hot_write import HotZaddRequest, register_hot_zadd_trim_script, zadd_hot_memory
from app.cache.memory_keys import memory_hot_key, memory_object_key
from app.config import Settings
from app.write.metrics import WRITE_CACHE_ERRORS
from app.write.models import MemoryRow, WriteOutcome, WriteOutcomeKind

logger = logging.getLogger(__name__)

_OBJECT_TTL = 3600


class CacheInvalidationError(RuntimeError):
    """A cache eviction that did not complete.

    Raised rather than swallowed: a forgotten memory's cached object still holds
    its content, so an eviction failure is a disclosure the caller has to record,
    not a warning to drop. The caller retries and, on exhaustion, writes the
    receipt the erasure ledger reads.
    """


@dataclass(frozen=True, slots=True)
class MemoryCacheWriter:
    redis: Redis
    settings: Settings
    _hot_zadd_trim: object | None = field(init=False, repr=False, compare=False, default=None)

    def object_key(self, org_id: UUID, memory_id: UUID) -> str:
        return memory_object_key(org_id, memory_id)

    def hot_key(self, org_id: UUID, agent_id: UUID) -> str:
        return memory_hot_key(org_id, agent_id)

    async def forget_memory(self, *, org_id: UUID, agent_id: UUID, memory_id: UUID) -> None:
        """Evict both cached copies, or raise so the caller can record the gap.

        Both operations are idempotent: DEL of an absent key and ZREM of an absent
        member are no-ops, so a retry after a partial failure is safe and a second
        forget of the same memory cannot corrupt another memory's state.
        """
        try:
            await self.redis.delete(self.object_key(org_id, memory_id))
            await self.redis.zrem(self.hot_key(org_id, agent_id), str(memory_id))
        except (OSError, RedisError) as exc:
            WRITE_CACHE_ERRORS.labels(op="forget_invalidate").inc()
            # Fixed message: the caller records this type name in a receipt, and
            # a Redis error can carry the endpoint, never memory content.
            raise CacheInvalidationError("memory cache eviction failed") from exc


    async def write_created(self, outcome: WriteOutcome) -> None:
        if outcome.kind != WriteOutcomeKind.CREATED:
            return
        memory = outcome.memory
        ttl = self.settings.memory_cache_ttl_seconds
        try:
            await self._write_object(memory, ttl)
        except (OSError, RedisError):
            WRITE_CACHE_ERRORS.labels(op="object_cache").inc()
            logger.warning(
                "object cache write failed org_id=%s memory_id=%s",
                memory.org_id,
                memory.id,
            )
        await self.refresh_hot(memory, ttl=ttl)

    async def refresh_hot(
        self,
        memory: MemoryRow,
        *,
        ttl: int | None = None,
    ) -> None:
        """Recompute and ZADD hot score. Fail-open on Redis errors."""
        resolved_ttl = ttl if ttl is not None else self.settings.memory_cache_ttl_seconds
        try:
            await self._write_hot(memory, resolved_ttl)
        except (OSError, RedisError):
            WRITE_CACHE_ERRORS.labels(op="hot_zset").inc()
            logger.warning(
                "hot cache write failed org_id=%s memory_id=%s",
                memory.org_id,
                memory.id,
            )

    async def _write_object(self, memory: MemoryRow, ttl: int) -> None:
        payload: dict[str, Any] = {
            "id": str(memory.id),
            "content": memory.content,
            "category": memory.category,
            "confidence": memory.confidence,
            "status": memory.status,
            "agent_id": str(memory.agent_id),
            "org_id": str(memory.org_id),
        }
        key = self.object_key(memory.org_id, memory.id)
        await self.redis.set(key, json.dumps(payload), ex=ttl)

    async def _write_hot(self, memory: MemoryRow, ttl: int) -> None:
        if self._hot_zadd_trim is None:
            object.__setattr__(self, "_hot_zadd_trim", register_hot_zadd_trim_script(self.redis))
        score = compute_hot_cache_score(memory, weights=self.settings.rank_weights())
        key = self.hot_key(memory.org_id, memory.agent_id)
        await zadd_hot_memory(
            self._hot_zadd_trim,
            HotZaddRequest(
                key=key,
                memory_id=memory.id,
                score=score,
                ttl_seconds=ttl,
            ),
        )
