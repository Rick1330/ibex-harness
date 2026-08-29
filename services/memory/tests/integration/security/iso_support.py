"""Shared helpers for ISO-* security integration tests (m3.E.1)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

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
from tests.integration.security.env import MemorySecurityTestEnv
from tests.integration.security.seed import seed_org_agent, seed_second_agent_same_org


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


def _hot_cache_probe(
    security_env: MemorySecurityTestEnv,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    scored_seed: ScoredMemorySeed,
    probe_org_id: UUID,
    probe_agent_id: UUID,
    flush_keys: tuple[tuple[UUID, UUID], ...],
) -> HotCacheIsolationProbe:
    return HotCacheIsolationProbe(
        session_factory=session_factory,
        cache_writer=security_env.cache_writer,
        hot_reader=security_env.hot_reader,
        redis=security_env.redis,
        scored_seed=scored_seed,
        probe_org_id=probe_org_id,
        probe_agent_id=probe_agent_id,
        flush_keys=flush_keys,
    )


async def build_iso_1_6_hot_cache_probe(
    session_factory: async_sessionmaker[AsyncSession],
    security_env: MemorySecurityTestEnv,
) -> HotCacheIsolationProbe:
    shared_agent_id = uuid4()
    org_a = await seed_org_agent(
        session_factory,
        slug_prefix="iso-hot-a",
        content="org a hot cache probe",
        agent_id=shared_agent_id,
    )
    return _hot_cache_probe(
        security_env,
        session_factory=session_factory,
        scored_seed=ScoredMemorySeed(
            org_id=org_a.org_id,
            agent_id=org_a.agent_id,
            content="org a exclusive hot memory",
        ),
        probe_org_id=security_env.orgs.org_b.org_id,
        probe_agent_id=shared_agent_id,
        flush_keys=(
            (org_a.org_id, org_a.agent_id),
            (security_env.orgs.org_b.org_id, shared_agent_id),
        ),
    )


async def build_iso_1_8_hot_cache_probe(
    session_factory: async_sessionmaker[AsyncSession],
    security_env: MemorySecurityTestEnv,
) -> HotCacheIsolationProbe:
    org_a = security_env.orgs.org_a
    agent_b = await seed_second_agent_same_org(
        session_factory,
        org_id=org_a.org_id,
        user_id=org_a.user_id,
        slug_prefix="iso-same-org",
    )
    return _hot_cache_probe(
        security_env,
        session_factory=session_factory,
        scored_seed=ScoredMemorySeed(
            org_id=org_a.org_id,
            agent_id=org_a.agent_id,
            content="agent a hot only",
        ),
        probe_org_id=org_a.org_id,
        probe_agent_id=agent_b,
        flush_keys=((org_a.org_id, org_a.agent_id),),
    )


HotCacheIsolationScenario = Callable[
    [async_sessionmaker[AsyncSession], MemorySecurityTestEnv],
    Awaitable[HotCacheIsolationProbe],
]

HOT_CACHE_ISOLATION_SCENARIOS: dict[str, HotCacheIsolationScenario] = {
    "iso_1_6": build_iso_1_6_hot_cache_probe,
    "iso_1_8": build_iso_1_8_hot_cache_probe,
}
