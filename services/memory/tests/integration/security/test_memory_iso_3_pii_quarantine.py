"""ISO-3.* PII and quarantine security integration tests (m3.E.1)."""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.read.models import FindSimilarQuery
from tests.integration.find_similar_support import upsert_embedding
from tests.integration.security.env import MemorySecurityTestEnv
from tests.integration.security.seed import (
    SHARED_ISO_QUERY_TEXT,
    DirectMemoryInsertParams,
    insert_direct_memory,
)

pytestmark = [pytest.mark.integration, pytest.mark.security_integration]


def _counter_value(name: str, labels: dict[str, str]) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    return float(value) if value is not None else 0.0


async def _find_similar_for_org(
    security_env: MemorySecurityTestEnv,
    *,
    query_vec: list[float],
    query_text: str,
) -> list:
    org_a = security_env.orgs.org_a
    return await security_env.read_repository.find_similar(
        FindSimilarQuery(
            org_id=org_a.org_id,
            agent_id=org_a.agent_id,
            query_embedding=query_vec,
            query_text=query_text,
            limit=10,
            min_similarity=0.0,
        )
    )


@pytest.mark.asyncio
async def test_memory_iso_3_1_tier1_pii_bypass_blocked_on_search(
    session_factory: async_sessionmaker[AsyncSession],
    security_env: MemorySecurityTestEnv,
) -> None:
    org_a = security_env.orgs.org_a
    bypass_id = await insert_direct_memory(
        session_factory,
        DirectMemoryInsertParams(
            org_id=org_a.org_id,
            agent_id=org_a.agent_id,
            content="Reach refunds at billing@example.com for dark mode help",
        ),
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

    results = await _find_similar_for_org(
        security_env,
        query_vec=query_vec,
        query_text=SHARED_ISO_QUERY_TEXT,
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
    safe_id = await insert_direct_memory(
        session_factory,
        DirectMemoryInsertParams(
            org_id=org_a.org_id,
            agent_id=org_a.agent_id,
            content="Contact [EMAIL_ADDRESS] for dark mode preference updates",
        ),
    )
    query_vec = await upsert_embedding(
        security_env.store,
        org_id=org_a.org_id,
        memory_id=safe_id,
        hotspot=8,
    )
    results = await _find_similar_for_org(
        security_env,
        query_vec=query_vec,
        query_text="dark mode preference",
    )
    assert safe_id in {item.id for item in results}


@pytest.mark.asyncio
async def test_memory_iso_3_2_quarantined_never_in_search(
    session_factory: async_sessionmaker[AsyncSession],
    security_env: MemorySecurityTestEnv,
) -> None:
    org_a = security_env.orgs.org_a
    quarantined_id = await insert_direct_memory(
        session_factory,
        DirectMemoryInsertParams(
            org_id=org_a.org_id,
            agent_id=org_a.agent_id,
            content="quarantined dark mode preference probe",
            status="quarantined",
        ),
    )
    query_vec = await upsert_embedding(
        security_env.store,
        org_id=org_a.org_id,
        memory_id=quarantined_id,
        hotspot=7,
    )
    results = await _find_similar_for_org(
        security_env,
        query_vec=query_vec,
        query_text="dark mode preference",
    )
    assert quarantined_id not in {item.id for item in results}
