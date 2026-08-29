"""ISO-1.* tenant isolation security integration tests (m3.E.1)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.permissions import MEMORY_READ
from app.vectorstore.base import SearchRequest, UpsertRequest
from tests.integration.conftest import with_service_org, zero_embedding
from tests.integration.find_similar_support import (
    SEARCH_HTTP_TOKEN,
    InsertActiveMemoryParams,
    insert_active_memory,
    search_http_client,
    upsert_embedding,
)
from tests.integration.hot_cache_support import ScoredMemorySeed
from tests.integration.security.env import MemorySecurityTestEnv
from tests.integration.security.iso_support import (
    HotCacheIsolationProbe,
    RlsCountQuery,
    assert_rls_count_zero,
    run_hot_cache_isolation_probe,
)
from tests.integration.security.seed import (
    SHARED_ISO_QUERY_TEXT,
    seed_org_agent,
    seed_second_agent_same_org,
)

pytestmark = [pytest.mark.integration, pytest.mark.security_integration]


@pytest.mark.asyncio
async def test_memory_iso_1_1_cross_org_search_empty(
    security_env: MemorySecurityTestEnv,
) -> None:
    org_a = security_env.orgs.org_a
    org_b = security_env.orgs.org_b
    await upsert_embedding(
        security_env.store,
        org_id=org_a.org_id,
        memory_id=org_a.memory_id,
        hotspot=3,
    )
    search_settings = security_env.settings.model_copy(
        update={
            "search_fallback_enabled": False,
        }
    )

    async with search_http_client(
        security_env.session_factory,
        search_settings,
        security_env.store,
        org_id=org_b.org_id,
    ) as client:
        response = await client.post(
            "/v1/memories/search",
            headers={"Authorization": f"Bearer {SEARCH_HTTP_TOKEN}"},
            json={
                "agent_id": str(org_b.agent_id),
                "query": SHARED_ISO_QUERY_TEXT,
                "limit": 10,
                "min_similarity": 0.0,
            },
        )

    assert response.status_code == 200
    results = response.json()["data"]["results"]
    assert results == []
    assert str(org_a.memory_id) not in {item["memory"]["id"] for item in results}


@pytest.mark.asyncio
async def test_memory_iso_1_2_cross_org_agent_forbidden(
    settings: Settings,
    security_env: MemorySecurityTestEnv,
) -> None:
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    org_a = security_env.orgs.org_a
    org_b = security_env.orgs.org_b
    cfg = settings.model_copy(update={"embedding_api_token": SecretStr("test-embed-token")})
    validator = StaticTokenValidator(
        {
            SEARCH_HTTP_TOKEN: ValidateResult(
                org_id=org_b.org_id,
                permissions=MEMORY_READ,
            )
        }
    )
    app = create_app(settings=cfg, validator=validator)
    async with app.router.lifespan_context(app), AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/memories/search",
            headers={"Authorization": f"Bearer {SEARCH_HTTP_TOKEN}"},
            json={
                "agent_id": str(org_a.agent_id),
                "query": SHARED_ISO_QUERY_TEXT,
                "limit": 5,
                "min_similarity": 0.0,
            },
        )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "AGENT_NOT_AUTHORIZED"
    assert org_b.org_id != org_a.org_id


@pytest.mark.asyncio
async def test_memory_iso_1_3_rls_floor_malformed_where(
    session_factory: async_sessionmaker[AsyncSession],
    security_env: MemorySecurityTestEnv,
) -> None:
    org_a = security_env.orgs.org_a
    org_b = security_env.orgs.org_b
    await assert_rls_count_zero(
        session_factory,
        RlsCountQuery(
            org_id=org_a.org_id,
            sql="""
                SELECT COUNT(*)::int AS c
                FROM ibex_core.memories
                WHERE id = :target_id
                """,
            params={"target_id": str(org_b.memory_id)},
        ),
    )


@pytest.mark.asyncio
async def test_memory_iso_1_4_relationship_cross_org_insert_rejected(
    session_factory: async_sessionmaker[AsyncSession],
    security_env: MemorySecurityTestEnv,
) -> None:
    org_a = security_env.orgs.org_a
    org_b = security_env.orgs.org_b
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_a.org_id)
        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    """
                    INSERT INTO ibex_core.memory_relationships (
                        org_id, source_memory_id, target_memory_id, relationship_type
                    ) VALUES (
                        :org_id, :source_id, :target_id, 'supersedes'
                    )
                    """
                ),
                {
                    "org_id": str(org_a.org_id),
                    "source_id": str(org_a.memory_id),
                    "target_id": str(org_b.memory_id),
                },
            )


@pytest.mark.asyncio
async def test_memory_iso_1_5_hnsw_no_cross_org_leakage(
    security_env: MemorySecurityTestEnv,
) -> None:
    org_a = security_env.orgs.org_a
    org_b = security_env.orgs.org_b
    vec = zero_embedding(hotspot=5)
    await security_env.store.upsert(
        UpsertRequest(
            memory_id=org_a.memory_id,
            org_id=org_a.org_id,
            embedding=vec,
            embedding_model="test",
        )
    )
    await security_env.store.upsert(
        UpsertRequest(
            memory_id=org_b.memory_id,
            org_id=org_b.org_id,
            embedding=vec,
            embedding_model="test",
        )
    )
    for ef_search in (10, 40, 100):
        hits = await security_env.store.search(
            SearchRequest(
                org_id=org_a.org_id,
                agent_id=org_a.agent_id,
                query_embedding=vec,
                limit=10,
                min_similarity=0.0,
                ef_search=ef_search,
            )
        )
        hit_ids = {item.memory_id for item in hits}
        assert org_b.memory_id not in hit_ids
        assert org_a.memory_id in hit_ids


@pytest.mark.asyncio
async def test_memory_iso_1_6_hot_cache_cross_org_same_agent_id(
    session_factory: async_sessionmaker[AsyncSession],
    security_env: MemorySecurityTestEnv,
) -> None:
    shared_agent_id = uuid4()
    org_a = await seed_org_agent(
        session_factory,
        slug_prefix="iso-hot-a",
        content="org a hot cache probe",
        agent_id=shared_agent_id,
    )
    await run_hot_cache_isolation_probe(
        HotCacheIsolationProbe(
            session_factory=session_factory,
            cache_writer=security_env.cache_writer,
            hot_reader=security_env.hot_reader,
            redis=security_env.redis,
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
    )


@pytest.mark.asyncio
async def test_memory_iso_1_7_conflict_escalations_rls_isolation(
    session_factory: async_sessionmaker[AsyncSession],
    security_env: MemorySecurityTestEnv,
) -> None:
    org_a = security_env.orgs.org_a
    org_b = security_env.orgs.org_b
    candidate_id = await insert_active_memory(
        session_factory,
        InsertActiveMemoryParams(
            org_id=org_a.org_id,
            agent_id=org_a.agent_id,
            content="iso escalation candidate memory",
        ),
    )
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_a.org_id)
        await session.execute(
            text(
                """
                INSERT INTO ibex_core.memory_conflict_escalations (
                    org_id, new_memory_id, candidate_memory_id, conflict_type, status
                ) VALUES (
                    :org_id, :new_id, :candidate_id, 'contradiction', 'pending'
                )
                """
            ),
            {
                "org_id": str(org_a.org_id),
                "new_id": str(org_a.memory_id),
                "candidate_id": str(candidate_id),
            },
        )
    await assert_rls_count_zero(
        session_factory,
        RlsCountQuery(
            org_id=org_b.org_id,
            sql="""
                SELECT COUNT(*)::int AS c
                FROM ibex_core.memory_conflict_escalations
                WHERE new_memory_id = :new_id
                """,
            params={"new_id": str(org_a.memory_id)},
        ),
    )


@pytest.mark.asyncio
async def test_memory_iso_1_8_hot_cache_same_org_cross_agent(
    session_factory: async_sessionmaker[AsyncSession],
    security_env: MemorySecurityTestEnv,
) -> None:
    org_a = security_env.orgs.org_a
    agent_b = await seed_second_agent_same_org(
        session_factory,
        org_id=org_a.org_id,
        user_id=org_a.user_id,
        slug_prefix="iso-same-org",
    )
    await run_hot_cache_isolation_probe(
        HotCacheIsolationProbe(
            session_factory=session_factory,
            cache_writer=security_env.cache_writer,
            hot_reader=security_env.hot_reader,
            redis=security_env.redis,
            scored_seed=ScoredMemorySeed(
                org_id=org_a.org_id,
                agent_id=org_a.agent_id,
                content="agent a hot only",
            ),
            probe_org_id=org_a.org_id,
            probe_agent_id=agent_b,
            flush_keys=((org_a.org_id, org_a.agent_id),),
        )
    )
