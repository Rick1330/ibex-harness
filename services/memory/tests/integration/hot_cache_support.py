"""Integration helpers for hot cache tests (m3.D.3)."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cache.hot_keys import hot_memories_key
from app.config import Settings
from app.read.hot_cache import MemoryHotCacheReader
from app.read.models import HotMemoryQuery
from app.write.cache import MemoryCacheWriter
from app.write.models import MemoryRow, WriteOutcome, WriteOutcomeKind
from tests.integration.conftest import seed_org_agent_memory
from tests.integration.find_similar_support import InsertScoredMemoryParams, insert_scored_memory
from tests.unit.memory_test_support import sample_memory_row


def redis_url() -> str | None:
    return os.getenv("IBEX_MEMORY_REDIS_URL") or os.getenv("REDIS_URL")


def require_redis_url() -> str:
    url = redis_url()
    if not url:
        pytest.skip("IBEX_MEMORY_REDIS_URL / REDIS_URL not set")
    return url


async def flush_hot_key(redis: Redis, org_id: UUID, agent_id: UUID) -> None:
    await redis.delete(hot_memories_key(org_id, agent_id))


def memory_row_from_params(
    memory_id: UUID,
    params: InsertScoredMemoryParams,
    *,
    retrieval_count: int = 0,
) -> MemoryRow:
    now = datetime.now(tz=UTC)
    return sample_memory_row(
        id=memory_id,
        org_id=params.org_id,
        agent_id=params.agent_id,
        content=params.content,
        category=params.category,
        usefulness_score=params.usefulness_score,
        confidence=params.confidence,
        retrieval_count=retrieval_count,
        valid_from=params.valid_from,
        created_at=now,
        updated_at=now,
    )


async def insert_and_write_hot(
    session_factory: async_sessionmaker[AsyncSession],
    writer: MemoryCacheWriter,
    params: InsertScoredMemoryParams,
    *,
    retrieval_count: int = 0,
) -> MemoryRow:
    memory_id = await insert_scored_memory(session_factory, params)
    row = memory_row_from_params(memory_id, params, retrieval_count=retrieval_count)
    await writer.write_created(WriteOutcome(kind=WriteOutcomeKind.CREATED, memory=row))
    return row


async def write_hot_rows(
    writer: MemoryCacheWriter,
    rows: list[MemoryRow],
) -> None:
    for row in rows:
        await writer.write_created(WriteOutcome(kind=WriteOutcomeKind.CREATED, memory=row))


async def seed_org_agent_with_redis(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    content: str = "hot cache seed memory",
) -> tuple[Redis, MemoryCacheWriter, MemoryHotCacheReader, UUID, UUID]:
    url = require_redis_url()
    redis = Redis.from_url(url)
    org_id, agent_id, _ = await seed_org_agent_memory(session_factory, content=content)
    await flush_hot_key(redis, org_id, agent_id)
    cfg = settings.model_copy(update={"redis_url": url})
    writer = MemoryCacheWriter(redis, cfg)
    reader = MemoryHotCacheReader(redis, session_factory)
    return redis, writer, reader, org_id, agent_id


async def read_hot(
    reader: MemoryHotCacheReader,
    org_id: UUID,
    agent_id: UUID,
    *,
    limit: int = 50,
) -> list:
    return await reader.get_hot_memories(
        HotMemoryQuery(org_id=org_id, agent_id=agent_id, limit=limit)
    )


def scored_params(
    *,
    org_id: UUID,
    agent_id: UUID,
    content: str,
    category: str = "factual",
    usefulness_score: float = 0.5,
    confidence: float = 0.8,
    age_days: float = 1.0,
) -> InsertScoredMemoryParams:
    now = datetime.now(tz=UTC)
    return InsertScoredMemoryParams(
        org_id=org_id,
        agent_id=agent_id,
        content=content,
        category=category,
        usefulness_score=usefulness_score,
        confidence=confidence,
        valid_from=now - timedelta(days=age_days),
    )
