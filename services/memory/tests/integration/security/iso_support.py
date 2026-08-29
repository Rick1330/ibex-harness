"""Shared helpers for ISO-* security integration tests (m3.E.1)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.read.hot_cache import MemoryHotCacheReader
from app.read.models import HotMemoryQuery
from app.write.cache import MemoryCacheWriter
from tests.integration.hot_cache_support import (
    ScoredMemorySeed,
    flush_hot_key,
    insert_and_write_hot,
    scored_params,
)
from tests.integration.memory_labels_write_support import with_org_rls


@dataclass(frozen=True, slots=True)
class RlsCountQuery:
    org_id: UUID
    sql: str
    params: dict[str, str]


async def assert_rls_count_zero(
    session_factory: async_sessionmaker[AsyncSession],
    query: RlsCountQuery,
) -> None:
    async with session_factory() as session, session.begin():
        await with_org_rls(session, query.org_id)
        count = (
            await session.execute(
                text(query.sql),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                query.params,
            )
        ).one()
    assert int(count.c) == 0


async def assert_hot_cache_empty(
    hot_reader: MemoryHotCacheReader,
    *,
    org_id: UUID,
    agent_id: UUID,
) -> None:
    results = await hot_reader.get_hot_memories(
        HotMemoryQuery(org_id=org_id, agent_id=agent_id, limit=10)
    )
    assert results == []


@dataclass(frozen=True, slots=True)
class HotCacheIsolationProbe:
    session_factory: async_sessionmaker[AsyncSession]
    cache_writer: MemoryCacheWriter
    hot_reader: MemoryHotCacheReader
    redis: Redis
    scored_seed: ScoredMemorySeed
    probe_org_id: UUID
    probe_agent_id: UUID
    flush_keys: tuple[tuple[UUID, UUID], ...]


async def run_hot_cache_isolation_probe(probe: HotCacheIsolationProbe) -> None:
    await insert_and_write_hot(
        probe.session_factory,
        probe.cache_writer,
        scored_params(probe.scored_seed),
    )
    try:
        await assert_hot_cache_empty(
            probe.hot_reader,
            org_id=probe.probe_org_id,
            agent_id=probe.probe_agent_id,
        )
    finally:
        for org_id, agent_id in probe.flush_keys:
            await flush_hot_key(probe.redis, org_id, agent_id)
