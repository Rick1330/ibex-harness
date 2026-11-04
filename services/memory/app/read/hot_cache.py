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
from app.read.conflicts import (
    collapse_conflict_pairs,
    conflict_groups_from_row,
    record_suppressed,
)
from app.read.metrics import HOT_CACHE_READ
from app.read.models import HotMemoryQuery, MemorySearchResult
from app.read.pii_guard import filter_pii_blocked_results

logger = logging.getLogger(__name__)

_HYDRATE_HOT_SQL = """
SELECT m.id, m.org_id, m.agent_id, m.content, m.category, m.confidence, m.status,
       m.created_at, m.updated_at, m.lifecycle_revision,
       COALESCE(
         (
           SELECT array_agg(e.id ORDER BY e.id)
           FROM ibex_core.memory_conflict_escalations e
           WHERE e.org_id = m.org_id
             AND e.status = 'pending'
             AND (e.new_memory_id = m.id OR e.candidate_memory_id = m.id)
         ),
         ARRAY[]::uuid[]
       ) AS conflict_groups
FROM ibex_core.memories m
WHERE m.org_id = :org_id
  AND m.agent_id = :agent_id
  AND m.id = ANY(CAST(:memory_ids AS uuid[]))
  AND m.confidence >= :min_confidence
  AND m.status = 'active'
  AND m.deleted_at IS NULL
  AND m.tombstoned = FALSE
  AND (m.expires_at IS NULL OR m.expires_at > CURRENT_TIMESTAMP)
  AND m.valid_from <= CURRENT_TIMESTAMP
  AND (m.valid_until IS NULL OR m.valid_until > CURRENT_TIMESTAMP)
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
        # Fetch a bounded reserve: suppression drops entries, and stopping at
        # ``limit`` would return a short page while an eligible entry sat just
        # below the cut. The reserve is the same 2x bound the fused path uses.
        fetch = min(query.limit * 2, HOT_CACHE_CAPACITY)
        try:
            raw = await self.redis.zrevrange(key, 0, fetch - 1, withscores=True)
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
        # PII before collapse, as on the search paths: a blocked winner must not
        # suppress its counterpart and then disappear itself.
        allowed = filter_pii_blocked_results(ordered)
        kept = self._collapse(allowed, query.suppress_conflicts)
        record_suppressed(len(allowed), len(kept))
        return kept[: query.limit]

    @staticmethod
    def _collapse(results: list[MemorySearchResult], enabled: bool) -> list[MemorySearchResult]:
        """Honour the same suppression switch as the search path (ADR-0094 amendment)."""
        if not enabled:
            return list(results)
        return collapse_conflict_pairs(results)

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
                lifecycle_revision=int(row.get("lifecycle_revision", 1)),
                conflict_groups=conflict_groups_from_row(row),
            )
        return out
