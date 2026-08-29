"""Latency smoke tests for find_similar (milestone 3.D.1 pre-merge gate)."""

from __future__ import annotations

import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.read.models import FindSimilarQuery
from app.vectorstore.pgvector_store import PgVectorStore
from tests.integration.find_similar_support import (
    InsertActiveMemoryParams,
    SeedAgentMemoriesParams,
    build_read_repository,
    insert_active_memory,
    seed_agent_with_memories,
)

pytestmark = pytest.mark.integration

_WARMUP_ITERATIONS = 5
_TIMED_ITERATIONS = 20
_VECTOR_ONLY_P95_BUDGET_MS = 100.0
_CORPUS_SIZE = 500


def _p95_ms(samples_ms: list[float]) -> float:
    ordered = sorted(samples_ms)
    index = max(0, int(len(ordered) * 0.95) - 1)
    return ordered[index]


@pytest.mark.asyncio
async def test_find_similar_latency_smoke(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: PgVectorStore,
) -> None:
    """Vector-only find_similar p95 must stay within the operational search budget on CI hardware."""
    seeded, _memory_ids, query_vec = await seed_agent_with_memories(
        session_factory,
        store,
        SeedAgentMemoriesParams(
            count=_CORPUS_SIZE,
            content_prefix="latency smoke dark mode",
            hotspot=1,
        ),
    )
    await insert_active_memory(
        session_factory,
        InsertActiveMemoryParams(
            org_id=seeded.org_id,
            agent_id=seeded.agent_id,
            content="lexical-only dark mode preference latency gate",
        ),
    )
    total_memories = _CORPUS_SIZE + 1
    repo = build_read_repository(session_factory, store, settings)
    query = FindSimilarQuery(
        org_id=seeded.org_id,
        agent_id=seeded.agent_id,
        query_embedding=query_vec,
        query_text="dark mode preference",
        limit=10,
        min_similarity=0.0,
    )

    for _ in range(_WARMUP_ITERATIONS):
        await repo.find_similar(query)

    vector_only_ms: list[float] = []
    for _ in range(_TIMED_ITERATIONS):
        start = time.perf_counter()
        results = await repo.find_similar(query)
        vector_only_ms.append((time.perf_counter() - start) * 1000)
        assert len(results) == 10
        assert all(item.source == "vector" for item in results)

    vector_p95 = _p95_ms(vector_only_ms)

    fts_query = FindSimilarQuery(
        org_id=seeded.org_id,
        agent_id=seeded.agent_id,
        query_embedding=query_vec,
        query_text="dark mode preference",
        limit=total_memories + 1,
        min_similarity=0.0,
    )
    fts_samples_ms: list[float] = []
    for _ in range(_TIMED_ITERATIONS):
        start = time.perf_counter()
        fts_results = await repo.find_similar(fts_query)
        fts_samples_ms.append((time.perf_counter() - start) * 1000)
        assert len(fts_results) == total_memories
        assert any(item.source == "full_text" for item in fts_results)

    fts_p95 = _p95_ms(fts_samples_ms)
    fts_delta_p95 = max(0.0, fts_p95 - vector_p95)

    assert vector_p95 < _VECTOR_ONLY_P95_BUDGET_MS, (
        f"vector-only find_similar p95 {vector_p95:.1f}ms exceeds "
        f"{_VECTOR_ONLY_P95_BUDGET_MS}ms budget; "
        f"fts_path_p95={fts_p95:.1f}ms fts_delta_p95={fts_delta_p95:.1f}ms"
    )
