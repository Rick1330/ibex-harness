"""PgVectorStore integration tests (requires migrated pgvector Postgres)."""

from __future__ import annotations

import asyncio
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.vectorstore.base import SearchRequest, UpsertRequest
from app.vectorstore.pgvector_store import PgVectorStore
from tests.integration.conftest import seed_org_agent_memory, zero_embedding

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_pgvector_upsert_search_delete(
    store: PgVectorStore,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_id, agent_id, memory_id = await seed_org_agent_memory(
        session_factory, content="vector search fixture"
    )
    query = zero_embedding(hotspot=0)
    await store.upsert(
        UpsertRequest(
            memory_id=memory_id,
            org_id=org_id,
            embedding=query,
            embedding_model="bge-m3",
        )
    )
    hits = await store.search(
        SearchRequest(
            org_id=org_id,
            agent_id=agent_id,
            query_embedding=query,
            limit=5,
            min_similarity=0.5,
            ef_search=40,
        )
    )
    assert len(hits) == 1
    assert hits[0].memory_id == memory_id
    assert hits[0].similarity == pytest.approx(1.0, abs=1e-6)

    await store.delete(memory_id=memory_id, org_id=org_id)
    hits_after = await store.search(
        SearchRequest(
            org_id=org_id,
            agent_id=agent_id,
            query_embedding=query,
            limit=5,
            min_similarity=0.5,
        )
    )
    assert hits_after == []


@pytest.mark.asyncio
async def test_pgvector_cross_org_isolation(
    store: PgVectorStore,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_a, agent_a, mem_a = await seed_org_agent_memory(session_factory, content="org-a")
    org_b, agent_b, mem_b = await seed_org_agent_memory(session_factory, content="org-b")
    vec_a = zero_embedding(hotspot=1)
    vec_b = zero_embedding(hotspot=2)
    await store.upsert(
        UpsertRequest(
            memory_id=mem_a, org_id=org_a, embedding=vec_a, embedding_model="bge-m3"
        )
    )
    await store.upsert(
        UpsertRequest(
            memory_id=mem_b, org_id=org_b, embedding=vec_b, embedding_model="bge-m3"
        )
    )

    hits_a = await store.search(
        SearchRequest(
            org_id=org_a,
            agent_id=agent_a,
            query_embedding=vec_a,
            limit=10,
            min_similarity=0.0,
        )
    )
    assert {h.memory_id for h in hits_a} == {mem_a}
    assert mem_b not in {h.memory_id for h in hits_a}

    hits_b = await store.search(
        SearchRequest(
            org_id=org_b,
            agent_id=agent_b,
            query_embedding=vec_b,
            limit=10,
            min_similarity=0.0,
        )
    )
    assert {h.memory_id for h in hits_b} == {mem_b}


@pytest.mark.asyncio
async def test_ef_search_set_local_no_cross_session_leak(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Two concurrent sessions set different hnsw.ef_search; neither leaks."""

    async def session_ef(value: int) -> int:
        async with session_factory() as session, session.begin():
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    "SELECT set_config('hnsw.ef_search', :ef, true)"
                ),
                {"ef": str(value)},
            )
            await asyncio.sleep(0.05)
            row = await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    "SELECT current_setting('hnsw.ef_search', true)"
                )
            )
            return int(row.scalar_one())

    left, right = await asyncio.gather(session_ef(16), session_ef(64))
    assert left == 16
    assert right == 64


@pytest.mark.asyncio
async def test_upsert_missing_memory_raises(
    store: PgVectorStore,
) -> None:
    request = UpsertRequest(
        memory_id=UUID("00000000-0000-0000-0000-000000000001"),
        org_id=UUID("00000000-0000-0000-0000-000000000002"),
        embedding=zero_embedding(),
        embedding_model="bge-m3",
    )
    with pytest.raises(LookupError):
        await store.upsert(request)


@pytest.mark.asyncio
async def test_search_rejects_invalid_limit(
    store: PgVectorStore,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_id, agent_id, _memory_id = await seed_org_agent_memory(
        session_factory, content="limit validation"
    )
    request = SearchRequest(
        org_id=org_id,
        agent_id=agent_id,
        query_embedding=zero_embedding(),
        limit=0,
    )
    with pytest.raises(ValueError, match="limit must be >= 1"):
        await store.search(request)
