"""Read-side hot memory sorted set consumer (milestone 3.D.3)."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cache.hot_keys import HOT_CACHE_CAPACITY, hot_memories_key
from app.org_context import set_service_org
from app.read.metrics import HOT_CACHE_READ
from app.read.models import HotMemoryQuery, MemorySearchResult
from app.read.pii_guard import filter_pii_blocked_results

logger = logging.getLogger(__name__)

_HYDRATE_HOT_SQL = """
SELECT id, org_id, agent_id, content, category, confidence, status,
       created_at, updated_at
FROM ibex_core.memories
WHERE org_id = :org_id
  AND agent_id = :agent_id
  AND id = ANY(CAST(:memory_ids AS uuid[]))
  AND confidence >= :min_confidence
  AND status = 'active'
  AND deleted_at IS NULL
"""


@dataclass(frozen=True, slots=True)
class _HydrateHotRequest:
    org_id: UUID
    agent_id: UUID
    memory_ids: list[UUID]
    min_confidence: float
    score_by_id: dict[UUID, float]


def _validate_min_confidence(value: float) -> None:
    if not math.isfinite(value):
        msg = "min_confidence must be in [0, 1]"
        raise ValueError(msg)
    if value < 0.0 or value > 1.0:
        msg = "min_confidence must be in [0, 1]"
        raise ValueError(msg)


def _validate_hot_query(query: HotMemoryQuery) -> None:
    if query.limit < 1:
        msg = "limit must be >= 1"
        raise ValueError(msg)
    if query.limit > HOT_CACHE_CAPACITY:
        msg = f"limit must be <= {HOT_CACHE_CAPACITY}"
        raise ValueError(msg)
    _validate_min_confidence(query.min_confidence)


@dataclass(frozen=True, slots=True)
class MemoryHotCacheReader:
    """ZREVRANGE read path for per-agent hot memories — not semantic search."""

    redis: Redis | None
    session_factory: async_sessionmaker[AsyncSession]

    async def get_hot_memories(self, query: HotMemoryQuery) -> list[MemorySearchResult]:
        _validate_hot_query(query)
        if self.redis is None:
            HOT_CACHE_READ.labels(result="empty").inc()
            return []

        key = hot_memories_key(query.org_id, query.agent_id)
        try:
            raw = await self.redis.zrevrange(key, 0, query.limit - 1, withscores=True)
        except (OSError, RedisError) as exc:
            HOT_CACHE_READ.labels(result="error").inc()
            logger.warning(
                "hot cache read failed org_id=%s agent_id=%s",
                query.org_id,
                query.agent_id,
                exc_info=exc,
            )
            return []

        if not raw:
            HOT_CACHE_READ.labels(result="empty").inc()
            return []

        ordered_ids: list[UUID] = []
        score_by_id: dict[UUID, float] = {}
        for member, score in raw:
            memory_id = UUID(member.decode() if isinstance(member, bytes) else member)
            ordered_ids.append(memory_id)
            score_by_id[memory_id] = float(score)

        hydrated = await self._hydrate_hot(
            _HydrateHotRequest(
                org_id=query.org_id,
                agent_id=query.agent_id,
                memory_ids=ordered_ids,
                min_confidence=query.min_confidence,
                score_by_id=score_by_id,
            )
        )
        if not hydrated:
            HOT_CACHE_READ.labels(result="empty").inc()
            return []

        HOT_CACHE_READ.labels(result="hit").inc()
        ordered = [hydrated[memory_id] for memory_id in ordered_ids if memory_id in hydrated]
        return filter_pii_blocked_results(ordered)

    async def _hydrate_hot(self, request: _HydrateHotRequest) -> dict[UUID, MemorySearchResult]:
        if not request.memory_ids:
            return {}
        ids = [str(memory_id) for memory_id in request.memory_ids]
        async with self.session_factory() as session, session.begin():
            await set_service_org(session, request.org_id)
            result = await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text  # nosec B608
                    _HYDRATE_HOT_SQL
                ),
                {
                    "org_id": str(request.org_id),
                    "agent_id": str(request.agent_id),
                    "memory_ids": ids,
                    "min_confidence": request.min_confidence,
                },
            )
            rows = result.mappings().all()

        out: dict[UUID, MemorySearchResult] = {}
        for row in rows:
            memory_id = UUID(str(row["id"]))
            out[memory_id] = MemorySearchResult(
                id=memory_id,
                org_id=UUID(str(row["org_id"])),
                agent_id=UUID(str(row["agent_id"])),
                content=str(row["content"]),
                category=str(row["category"]),
                confidence=float(row["confidence"]),
                status=str(row["status"]),
                similarity=request.score_by_id[memory_id],
                source="hot_cache",
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        return out
