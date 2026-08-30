"""MemorySecurityTestEnv fixture (m3.E.1 — port of Go securityTestEnv)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.read.hot_cache import MemoryHotCacheReader
from app.read.repository import MemoryReadRepository
from app.vectorstore.pgvector_store import PgVectorStore
from app.write.cache import MemoryCacheWriter
from tests.integration.find_similar_support import build_read_repository
from tests.integration.security.seed import TwoOrgSeed, require_redis_url, seed_two_orgs


@dataclass(frozen=True, slots=True)
class MemorySecurityTestEnv:
    session_factory: async_sessionmaker[AsyncSession]
    settings: Settings
    store: PgVectorStore
    redis: Redis
    cache_writer: MemoryCacheWriter
    hot_reader: MemoryHotCacheReader
    read_repository: MemoryReadRepository
    orgs: TwoOrgSeed


@pytest_asyncio.fixture
async def security_env(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: PgVectorStore,
) -> AsyncIterator[MemorySecurityTestEnv]:
    url = require_redis_url()
    redis = Redis.from_url(url)
    cfg = settings.model_copy(update={"redis_url": url})
    orgs = await seed_two_orgs(session_factory)
    try:
        yield MemorySecurityTestEnv(
            session_factory=session_factory,
            settings=cfg,
            store=store,
            redis=redis,
            cache_writer=MemoryCacheWriter(redis, cfg),
            hot_reader=MemoryHotCacheReader(redis, session_factory),
            read_repository=build_read_repository(session_factory, store, cfg),
            orgs=orgs,
        )
    finally:
        await redis.aclose()
