"""HTTP integration tests for composite search ranking (milestone 3.D.2)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.read.models import FindSimilarQuery
from app.vectorstore.pgvector_store import PgVectorStore
from tests.integration.find_similar_support import (
    SEARCH_HTTP_TOKEN,
    InsertActiveMemoryParams,
    SeedCompositeRankingParams,
    SeedCompositeRankingRequest,
    build_read_repository,
    insert_active_memory,
    search_http_client,
    seed_composite_ranking_pair,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_http_composite_ranking_old_factual_beats_fresh_episodic(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: PgVectorStore,
) -> None:
    seed = await seed_composite_ranking_pair(
        SeedCompositeRankingRequest(session_factory, store)
    )

    async with search_http_client(
        session_factory, settings, store, org_id=seed.org_id
    ) as client:
        response = await client.post(
            "/v1/memories/search",
            headers={"Authorization": f"Bearer {SEARCH_HTTP_TOKEN}"},
            json={
                "agent_id": str(seed.agent_id),
                "query": "dark mode preference",
                "limit": 5,
                "min_similarity": 0.0,
            },
        )

    assert response.status_code == 200
    body = response.json()
    results = body["data"]["results"]
    assert len(results) >= 2
    assert results[0]["memory"]["category"] == "factual"
    assert results[0]["memory"]["id"] == str(seed.factual_id)
    assert results[1]["memory"]["category"] == "episodic"


@pytest.mark.asyncio
async def test_find_similar_composite_ranking_old_factual_beats_fresh_episodic(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: PgVectorStore,
) -> None:
    seed = await seed_composite_ranking_pair(
        SeedCompositeRankingRequest(session_factory, store)
    )
    repo = build_read_repository(session_factory, store, settings)
    results = await repo.find_similar(
        FindSimilarQuery(
            org_id=seed.org_id,
            agent_id=seed.agent_id,
            query_embedding=seed.query_vec,
            query_text="dark mode preference",
            limit=5,
            min_similarity=0.0,
        )
    )
    assert len(results) >= 2
    assert results[0].category == "factual"
    assert results[0].id == seed.factual_id


@pytest.mark.asyncio
async def test_composite_ranking_vector_beats_fts_supplement(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: PgVectorStore,
) -> None:
    seed = await seed_composite_ranking_pair(
        SeedCompositeRankingRequest(
            session_factory,
            store,
            SeedCompositeRankingParams(hotspot=4),
        )
    )
    fts_only = await insert_active_memory(
        session_factory,
        InsertActiveMemoryParams(
            org_id=seed.org_id,
            agent_id=seed.agent_id,
            content="lexical-only composite fts dark mode interface preference gate",
        ),
    )

    repo = build_read_repository(session_factory, store, settings)
    results = await repo.find_similar(
        FindSimilarQuery(
            org_id=seed.org_id,
            agent_id=seed.agent_id,
            query_embedding=seed.query_vec,
            query_text="dark mode preference",
            limit=5,
            min_similarity=0.0,
        )
    )

    assert len(results) >= 3
    assert results[0].source == "vector"
    assert results[0].id in {seed.factual_id, seed.episodic_id}
    fts_results = [item for item in results if item.source == "full_text"]
    assert fts_results
    assert fts_only in {item.id for item in fts_results}
    vector_positions = [
        index
        for index, item in enumerate(results)
        if item.source == "vector"
    ]
    fts_positions = [
        index for index, item in enumerate(results) if item.source == "full_text"
    ]
    assert min(vector_positions) < min(fts_positions)
