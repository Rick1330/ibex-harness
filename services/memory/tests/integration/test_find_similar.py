"""Integration tests for find_similar read path (milestone 3.D.1)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.read.metrics import SEARCH_FALLBACK
from app.read.models import FindSimilarQuery
from app.vectorstore.pgvector_store import PgVectorStore
from tests.integration.conftest import seed_org_agent_memory, with_service_org
from tests.integration.find_similar_support import (
    SEARCH_HTTP_TOKEN,
    InsertActiveMemoryParams,
    SeedAgentMemoriesParams,
    build_read_repository,
    insert_active_memory,
    search_http_client,
    seed_agent_with_memories,
    upsert_embedding,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_find_similar_cross_org_isolation(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: PgVectorStore,
) -> None:
    org_a, agent_a, mem_a = await seed_org_agent_memory(
        session_factory, content="org a prefers concise technical summaries"
    )
    org_b, _agent_b, mem_b = await seed_org_agent_memory(
        session_factory, content="org b prefers concise technical summaries"
    )
    query_vec = await upsert_embedding(store, org_id=org_a, memory_id=mem_a, hotspot=1)
    await upsert_embedding(store, org_id=org_b, memory_id=mem_b, hotspot=1)

    repo = build_read_repository(session_factory, store, settings)
    results = await repo.find_similar(
        FindSimilarQuery(
            org_id=org_a,
            agent_id=agent_a,
            query_embedding=query_vec,
            query_text="concise technical summaries",
            limit=10,
            min_similarity=0.0,
        )
    )
    assert {item.id for item in results} == {mem_a}


@pytest.mark.asyncio
async def test_find_similar_cross_agent_isolation(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: PgVectorStore,
) -> None:
    org_id, agent_a, mem_a = await seed_org_agent_memory(
        session_factory, content="agent a dark mode preference"
    )
    agent_b = uuid4()
    mem_b = uuid4()
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_id)
        user_row = await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT id FROM ibex_core.users WHERE org_id = :org LIMIT 1"
            ),
            {"org": str(org_id)},
        )
        user_id = user_row.scalar_one()
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                """
                INSERT INTO ibex_core.agents (id, org_id, created_by, name, slug)
                VALUES (:id, :org_id, :created_by, :name, :slug)
                """
            ),
            {
                "id": str(agent_b),
                "org_id": str(org_id),
                "created_by": str(user_id),
                "name": "Agent B",
                "slug": f"agent-{agent_b.hex[:8]}",
            },
        )
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                """
                INSERT INTO ibex_core.memories (
                    id, org_id, agent_id, content, content_hash, content_tokens
                ) VALUES (
                    :id, :org_id, :agent_id, :content, :hash, :tokens
                )
                """
            ),
            {
                "id": str(mem_b),
                "org_id": str(org_id),
                "agent_id": str(agent_b),
                "content": "agent b dark mode preference",
                "hash": f"hash-{mem_b.hex}",
                "tokens": 4,
            },
        )

    query_vec = await upsert_embedding(store, org_id=org_id, memory_id=mem_a, hotspot=2)
    await upsert_embedding(store, org_id=org_id, memory_id=mem_b, hotspot=2)

    repo = build_read_repository(session_factory, store, settings)
    results = await repo.find_similar(
        FindSimilarQuery(
            org_id=org_id,
            agent_id=agent_a,
            query_embedding=query_vec,
            query_text="dark mode",
            limit=10,
            min_similarity=0.0,
        )
    )
    assert all(item.agent_id == agent_a for item in results)
    assert mem_b not in {item.id for item in results}


@pytest.mark.asyncio
async def test_find_similar_excludes_quarantined_and_deleted(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: PgVectorStore,
) -> None:
    org_id, agent_id, _ = await seed_org_agent_memory(session_factory, content="seed")
    active_id = await insert_active_memory(
        session_factory,
        InsertActiveMemoryParams(
            org_id=org_id,
            agent_id=agent_id,
            content="active preference dark mode",
        ),
    )
    quarantined_id = await insert_active_memory(
        session_factory,
        InsertActiveMemoryParams(
            org_id=org_id,
            agent_id=agent_id,
            content="quarantined preference dark mode",
            status="quarantined",
        ),
    )
    deleted_id = await insert_active_memory(
        session_factory,
        InsertActiveMemoryParams(
            org_id=org_id,
            agent_id=agent_id,
            content="deleted preference dark mode",
        ),
    )
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_id)
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "UPDATE ibex_core.memories SET deleted_at = NOW() WHERE id = :id"
            ),
            {"id": str(deleted_id)},
        )
    query_vec = await upsert_embedding(store, org_id=org_id, memory_id=active_id, hotspot=4)
    await upsert_embedding(store, org_id=org_id, memory_id=quarantined_id, hotspot=4)

    repo = build_read_repository(session_factory, store, settings)
    results = await repo.find_similar(
        FindSimilarQuery(
            org_id=org_id,
            agent_id=agent_id,
            query_embedding=query_vec,
            query_text="dark mode preference",
            limit=10,
            min_similarity=0.0,
        )
    )
    assert {item.id for item in results} == {active_id}


@pytest.mark.asyncio
async def test_find_similar_sparse_agent_triggers_fallback(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: PgVectorStore,
) -> None:
    org_id, agent_id, mem_id = await seed_org_agent_memory(
        session_factory, content="vector only dark mode preference"
    )
    fts_only = await insert_active_memory(
        session_factory,
        InsertActiveMemoryParams(
            org_id=org_id,
            agent_id=agent_id,
            content="lexical preference dark mode interface only",
        ),
    )
    query_vec = await upsert_embedding(store, org_id=org_id, memory_id=mem_id, hotspot=5)

    repo = build_read_repository(session_factory, store, settings)
    results = await repo.find_similar(
        FindSimilarQuery(
            org_id=org_id,
            agent_id=agent_id,
            query_embedding=query_vec,
            query_text="dark mode preference",
            limit=3,
            min_similarity=0.0,
        )
    )
    assert len(results) >= 2
    assert results[0].source == "vector"
    assert any(item.source == "full_text" for item in results)
    assert fts_only in {item.id for item in results}


def _fallback_metric_value() -> float:
    return SEARCH_FALLBACK.labels(triggered="true")._value.get()


@pytest.mark.asyncio
async def test_find_similar_fts_when_limit_exceeds_corpus(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: PgVectorStore,
) -> None:
    seeded, _memory_ids, query_vec = await seed_agent_with_memories(
        session_factory,
        store,
        SeedAgentMemoriesParams(
            count=15,
            content_prefix="corpus limit gate dark mode",
            hotspot=2,
        ),
    )
    fts_only = await insert_active_memory(
        session_factory,
        InsertActiveMemoryParams(
            org_id=seeded.org_id,
            agent_id=seeded.agent_id,
            content="lexical-only dark mode interface preference gate",
        ),
    )
    before = _fallback_metric_value()
    repo = build_read_repository(session_factory, store, settings)
    results = await repo.find_similar(
        FindSimilarQuery(
            org_id=seeded.org_id,
            agent_id=seeded.agent_id,
            query_embedding=query_vec,
            query_text="dark mode preference",
            limit=20,
            min_similarity=0.0,
        )
    )
    assert _fallback_metric_value() > before
    assert len(results) <= 20
    assert len({item.id for item in results}) == len(results)
    assert len(results) == 16
    assert fts_only in {item.id for item in results}
    assert any(item.source == "full_text" for item in results)


@pytest.mark.asyncio
async def test_find_similar_no_fts_when_vector_fills_limit(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: PgVectorStore,
) -> None:
    seeded, _memory_ids, query_vec = await seed_agent_with_memories(
        session_factory,
        store,
        SeedAgentMemoriesParams(
            count=5,
            content_prefix="vector fill gate dark mode",
            hotspot=4,
        ),
    )
    before = _fallback_metric_value()
    repo = build_read_repository(session_factory, store, settings)
    results = await repo.find_similar(
        FindSimilarQuery(
            org_id=seeded.org_id,
            agent_id=seeded.agent_id,
            query_embedding=query_vec,
            query_text="dark mode preference",
            limit=3,
            min_similarity=0.0,
        )
    )
    assert _fallback_metric_value() == before
    assert len(results) == 3
    assert all(item.source == "vector" for item in results)


@pytest.mark.asyncio
async def test_find_similar_punctuation_query_degrades_gracefully(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: PgVectorStore,
) -> None:
    org_id, agent_id, mem_id = await seed_org_agent_memory(
        session_factory, content="preference content"
    )
    query_vec = await upsert_embedding(store, org_id=org_id, memory_id=mem_id, hotspot=6)

    repo = build_read_repository(session_factory, store, settings)
    results = await repo.find_similar(
        FindSimilarQuery(
            org_id=org_id,
            agent_id=agent_id,
            query_embedding=query_vec,
            query_text="!!!",
            limit=5,
            min_similarity=0.0,
        )
    )
    assert len(results) == 1
    assert results[0].id == mem_id


@pytest.mark.asyncio
async def test_http_post_search(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: PgVectorStore,
) -> None:
    org_id, agent_id, mem_id = await seed_org_agent_memory(
        session_factory, content="http search dark mode preference"
    )
    await upsert_embedding(store, org_id=org_id, memory_id=mem_id, hotspot=7)

    async with search_http_client(
        session_factory, settings, store, org_id=org_id
    ) as client:
        response = await client.post(
            "/v1/memories/search",
            headers={"Authorization": f"Bearer {SEARCH_HTTP_TOKEN}"},
            json={
                "agent_id": str(agent_id),
                "query": "dark mode preference",
                "limit": 5,
                "min_similarity": 0.0,
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["results"]
    assert body["data"]["results"][0]["memory"]["id"] == str(mem_id)


@pytest.mark.asyncio
async def test_schema_indexes_exist(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        result = await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                """
                SELECT c.relname, am.amname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_am am ON am.oid = c.relam
                WHERE n.nspname = 'ibex_core'
                  AND c.relname IN (
                    'idx_memories_embedding_hnsw',
                    'idx_memories_search_vector'
                  )
                ORDER BY c.relname
                """
            )
        )
        rows = {row.relname: row.amname for row in result}
    assert rows["idx_memories_embedding_hnsw"] == "hnsw"
    assert rows["idx_memories_search_vector"] == "gin"
