"""ISO-3.* PII and quarantine security integration tests (m3.E.1)."""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.read.models import FindSimilarQuery
from tests.integration.conftest import with_service_org
from tests.integration.find_similar_support import upsert_embedding
from tests.integration.security.env import MemorySecurityTestEnv
from tests.integration.security.seed import SHARED_ISO_QUERY_TEXT

pytestmark = [pytest.mark.integration, pytest.mark.security_integration]


def _counter_value(name: str, labels: dict[str, str]) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    return float(value) if value is not None else 0.0


@pytest.mark.asyncio
async def test_memory_iso_3_1_tier1_pii_bypass_blocked_on_search(
    session_factory: async_sessionmaker[AsyncSession],
    security_env: MemorySecurityTestEnv,
) -> None:
    org_a = security_env.orgs.org_a
    bypass_id = await _insert_direct_memory(
        session_factory,
        org_id=org_a.org_id,
        agent_id=org_a.agent_id,
        content="Reach refunds at billing@example.com for dark mode help",
        status="active",
    )
    query_vec = await upsert_embedding(
        security_env.store,
        org_id=org_a.org_id,
        memory_id=bypass_id,
        hotspot=7,
    )
    before_blocked = _counter_value(
        "ibex_memory_read_pii_reconfirm_total", {"result": "blocked"}
    )

    results = await security_env.read_repository.find_similar(
        FindSimilarQuery(
            org_id=org_a.org_id,
            agent_id=org_a.agent_id,
            query_embedding=query_vec,
            query_text=SHARED_ISO_QUERY_TEXT,
            limit=10,
            min_similarity=0.0,
        )
    )
    assert bypass_id not in {item.id for item in results}
    after_blocked = _counter_value(
        "ibex_memory_read_pii_reconfirm_total", {"result": "blocked"}
    )
    assert after_blocked > before_blocked


@pytest.mark.asyncio
async def test_memory_iso_3_1_placeholder_content_not_blocked(
    session_factory: async_sessionmaker[AsyncSession],
    security_env: MemorySecurityTestEnv,
) -> None:
    org_a = security_env.orgs.org_a
    safe_id = await _insert_direct_memory(
        session_factory,
        org_id=org_a.org_id,
        agent_id=org_a.agent_id,
        content="Contact [EMAIL_ADDRESS] for dark mode preference updates",
        status="active",
    )
    query_vec = await upsert_embedding(
        security_env.store,
        org_id=org_a.org_id,
        memory_id=safe_id,
        hotspot=8,
    )
    results = await security_env.read_repository.find_similar(
        FindSimilarQuery(
            org_id=org_a.org_id,
            agent_id=org_a.agent_id,
            query_embedding=query_vec,
            query_text="dark mode preference",
            limit=10,
            min_similarity=0.0,
        )
    )
    assert safe_id in {item.id for item in results}


@pytest.mark.asyncio
async def test_memory_iso_3_2_quarantined_never_in_search(
    session_factory: async_sessionmaker[AsyncSession],
    security_env: MemorySecurityTestEnv,
) -> None:
    org_a = security_env.orgs.org_a
    quarantined_id = await _insert_direct_memory(
        session_factory,
        org_id=org_a.org_id,
        agent_id=org_a.agent_id,
        content="quarantined dark mode preference probe",
        status="quarantined",
    )
    query_vec = await upsert_embedding(
        security_env.store,
        org_id=org_a.org_id,
        memory_id=quarantined_id,
        hotspot=7,
    )
    results = await security_env.read_repository.find_similar(
        FindSimilarQuery(
            org_id=org_a.org_id,
            agent_id=org_a.agent_id,
            query_embedding=query_vec,
            query_text="dark mode preference",
            limit=10,
            min_similarity=0.0,
        )
    )
    assert quarantined_id not in {item.id for item in results}


async def _insert_direct_memory(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    org_id,
    agent_id,
    content: str,
    status: str,
):
    from uuid import uuid4

    memory_id = uuid4()
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_id)
        await session.execute(
            text(
                """
                INSERT INTO ibex_core.memories (
                    id, org_id, agent_id, content, content_hash, content_tokens, status
                ) VALUES (
                    :id, :org_id, :agent_id, :content, :hash, :tokens, :status
                )
                """
            ),
            {
                "id": str(memory_id),
                "org_id": str(org_id),
                "agent_id": str(agent_id),
                "content": content,
                "hash": f"hash-{memory_id.hex}",
                "tokens": max(1, len(content.split())),
                "status": status,
            },
        )
    return memory_id
