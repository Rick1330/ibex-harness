"""Redis object cache + hot sorted-set writes (m3.C.5 / ADR-0057)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import Settings
from app.scoring import CompositeInputs, composite_score
from app.write.metrics import WRITE_CACHE_ERRORS
from app.write.models import MemoryRow, WriteOutcome, WriteOutcomeKind

logger = logging.getLogger(__name__)

_OBJECT_TTL = 3600
_HOT_TTL = 3600


@dataclass(frozen=True, slots=True)
class MemoryCacheWriter:
    redis: Redis
    settings: Settings

    def object_key(self, org_id: UUID, memory_id: UUID) -> str:
        return f"{org_id}:memory:{memory_id}"

    def hot_key(self, org_id: UUID, agent_id: UUID) -> str:
        return f"{org_id}:hot_memories:{agent_id}"

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
        try:
            await self._write_hot(memory, ttl)
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
        now = datetime.now(tz=UTC)
        age_days = max(0.0, (now - memory.valid_from).total_seconds() / 86400.0)
        score = composite_score(
            CompositeInputs(
                relevance=1.0,
                age_days=age_days,
                categories=(memory.category,),
                usefulness=float(memory.usefulness_score),
                confidence=float(memory.confidence),
                access_frequency=min(1.0, memory.retrieval_count / 10.0),
            )
        )
        key = self.hot_key(memory.org_id, memory.agent_id)
        await self.redis.zadd(key, {str(memory.id): score})
        await self.redis.expire(key, ttl)
