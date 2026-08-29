"""Integration tests for hot cache stale-ID filtering (m3.D.3)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cache.hot_keys import hot_memories_key
from app.cache.hot_score import compute_hot_cache_score
from tests.integration.conftest import with_service_org
from tests.integration.hot_cache_support import (
    flush_hot_key,
    insert_and_write_hot,
    read_hot,
    scored_params,
    seed_org_agent_with_redis,
)
from tests.unit.memory_test_support import sample_memory_row

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_hot_cache_hydrate_filters_soft_deleted_memory(
    session_factory: async_sessionmaker[AsyncSession],
    settings,
) -> None:
    redis, writer, reader, org_id, agent_id = await seed_org_agent_with_redis(
        session_factory, settings
    )
    try:
        row = await insert_and_write_hot(
            session_factory,
            writer,
            scored_params(
                org_id=org_id,
                agent_id=agent_id,
                content="will be soft deleted",
            ),
        )
        key = hot_memories_key(org_id, agent_id)
        assert await redis.zscore(key, str(row.id)) is not None

        async with session_factory() as session, session.begin():
            await with_service_org(session, org_id)
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    "UPDATE ibex_core.memories SET deleted_at = NOW() WHERE id = :id"
                ),
                {"id": str(row.id)},
            )

        results = await read_hot(reader, org_id, agent_id, limit=10)
        assert results == []
    finally:
        await flush_hot_key(redis, org_id, agent_id)
        await redis.aclose()


@pytest.mark.asyncio
async def test_hot_cache_hydrate_filters_superseded_memory(
    session_factory: async_sessionmaker[AsyncSession],
    settings,
) -> None:
    redis, writer, reader, org_id, agent_id = await seed_org_agent_with_redis(
        session_factory, settings
    )
    try:
        row = await insert_and_write_hot(
            session_factory,
            writer,
            scored_params(
                org_id=org_id,
                agent_id=agent_id,
                content="superseded hot cache row",
            ),
        )
        async with session_factory() as session, session.begin():
            await with_service_org(session, org_id)
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    "UPDATE ibex_core.memories SET status = 'superseded' WHERE id = :id"
                ),
                {"id": str(row.id)},
            )

        results = await read_hot(reader, org_id, agent_id, limit=10)
        assert results == []
    finally:
        await flush_hot_key(redis, org_id, agent_id)
        await redis.aclose()


@pytest.mark.asyncio
async def test_hot_cache_orphan_zset_member_without_db_row(
    session_factory: async_sessionmaker[AsyncSession],
    settings,
) -> None:
    redis, _, reader, org_id, agent_id = await seed_org_agent_with_redis(
        session_factory, settings
    )
    try:
        orphan_id = uuid4()
        key = hot_memories_key(org_id, agent_id)
        score = compute_hot_cache_score(
            sample_memory_row(org_id=org_id, agent_id=agent_id)
        )
        await redis.zadd(key, {str(orphan_id): score})

        results = await read_hot(reader, org_id, agent_id, limit=10)
        assert results == []
    finally:
        await flush_hot_key(redis, org_id, agent_id)
        await redis.aclose()
