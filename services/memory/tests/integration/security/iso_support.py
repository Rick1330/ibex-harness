"""Shared helpers for ISO-* security integration tests (m3.E.1)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.read.hot_cache import MemoryHotCacheReader
from app.read.models import HotMemoryQuery
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
