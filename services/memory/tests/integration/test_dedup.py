"""Integration: exact hash bump + near-dup via PgVectorStore (org-scoped)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.dedup.hash import content_hash_sha256
from app.dedup.persist import (
    ExactHashLookup,
    RetrievalBump,
    find_active_by_content_hash,
    increment_retrieval_count,
)
from app.dedup.service import DedupService
from app.pipeline import (
    EmbedStage,
    ExactDedupStage,
    NearDedupStage,
    ValidateStage,
    WriteContext,
    WritePipeline,
)
from app.vectorstore.base import SearchRequest, UpsertRequest
from app.vectorstore.pgvector_store import PgVectorStore
from tests.integration.conftest import seed_org_agent_memory, zero_embedding

pytestmark = pytest.mark.integration


async def _set_content_hash(
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id: UUID,
    memory_id: UUID,
    content_hash: str,
) -> None:
    async with factory() as session, session.begin():
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.is_service_account', 'true', true)"
            )
        )
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.current_org_id', :org_id, true)"
            ),
            {"org_id": str(org_id)},
        )
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                """
                UPDATE ibex_core.memories
                SET content_hash = :hash
                WHERE id = :id AND org_id = :org_id
                """
            ),
            {"hash": content_hash, "id": str(memory_id), "org_id": str(org_id)},
        )


@pytest.mark.asyncio
async def test_exact_hit_increments_retrieval_count(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    content = "Exact duplicate payload for m3.C.2"
    digest = content_hash_sha256(content)
    org_id, agent_id, memory_id = await seed_org_agent_memory(
        session_factory, content=content
    )
    await _set_content_hash(
        session_factory, org_id=org_id, memory_id=memory_id, content_hash=digest
    )

    async def lookup(o: UUID, a: UUID, h: str) -> UUID | None:
        return await find_active_by_content_hash(
            session_factory, ExactHashLookup(org_id=o, agent_id=a, content_hash=h)
        )

    async def bump(o: UUID, mid: UUID) -> int:
        return await increment_retrieval_count(
            session_factory, RetrievalBump(org_id=o, memory_id=mid)
        )

    dedup = DedupService(settings, exact_lookup=lookup, bump_retrieval=bump)
    pipe = WritePipeline([ValidateStage(settings), ExactDedupStage(dedup)])
    ctx = await pipe.run(
        WriteContext(org_id=org_id, agent_id=agent_id, content=content)
    )
    assert ctx.is_exact_duplicate is True
    assert ctx.existing_memory_id == memory_id
    assert ctx.stop is True

    async with session_factory() as session:
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.is_service_account', 'true', true)"
            )
        )
        count = (
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    """
                    SELECT retrieval_count FROM ibex_core.memories
                    WHERE id = :id AND org_id = :org
                    """
                ),
                {"id": str(memory_id), "org": str(org_id)},
            )
        ).scalar_one()
    assert int(count) == 1


@pytest.mark.asyncio
async def test_exact_cross_tenant_no_match(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    content = "Shared wording different orgs"
    digest = content_hash_sha256(content)
    org_a, agent_a, mem_a = await seed_org_agent_memory(session_factory, content=content)
    org_b, _agent_b, _mem_b = await seed_org_agent_memory(session_factory, content=content)
    await _set_content_hash(
        session_factory, org_id=org_a, memory_id=mem_a, content_hash=digest
    )

    found = await find_active_by_content_hash(
        session_factory,
        ExactHashLookup(org_id=org_b, agent_id=agent_a, content_hash=digest),
    )
    assert found is None
    found_ok = await find_active_by_content_hash(
        session_factory,
        ExactHashLookup(org_id=org_a, agent_id=agent_a, content_hash=digest),
    )
    assert found_ok == mem_a


@pytest.mark.asyncio
async def test_near_dup_via_pgvector_org_scoped(
    store: PgVectorStore,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    content = "Near duplicate vector search"
    org_a, agent_a, mem_a = await seed_org_agent_memory(session_factory, content=content)
    org_b, _agent_b, mem_b = await seed_org_agent_memory(session_factory, content=content)
    vec = zero_embedding(hotspot=7)
    await store.upsert(
        UpsertRequest(
            memory_id=mem_a,
            org_id=org_a,
            embedding=vec,
            embedding_model="test-model",
        )
    )
    await store.upsert(
        UpsertRequest(
            memory_id=mem_b,
            org_id=org_b,
            embedding=vec,
            embedding_model="test-model",
        )
    )

    async def lookup(_o: UUID, _a: UUID, _h: str) -> UUID | None:
        return None

    dedup = DedupService(
        Settings(
            database_url=settings.database_url,
            near_duplicate_sim_threshold=0.92,
            near_duplicate_candidate_limit=5,
        ),
        store=store,
        exact_lookup=lookup,
    )

    async def embed(_text: str) -> list[float]:
        return list(vec)

    pipe = WritePipeline(
        [
            ValidateStage(settings),
            ExactDedupStage(dedup),
            EmbedStage(embed),
            NearDedupStage(dedup),
        ]
    )
    ctx = await pipe.run(
        WriteContext(org_id=org_a, agent_id=agent_a, content="another write")
    )
    assert mem_a in ctx.near_duplicate_candidates
    assert mem_b not in ctx.near_duplicate_candidates

    empty_agent = uuid4()
    hits = await store.search(
        SearchRequest(
            org_id=org_a,
            agent_id=empty_agent,
            query_embedding=vec,
            limit=5,
            min_similarity=0.5,
        )
    )
    assert hits == []
