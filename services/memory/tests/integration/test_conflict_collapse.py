"""Postgres integration coverage for unresolved-conflict suppression (5.B.2).

The pair is seeded as a pending ``memory_conflict_escalations`` row because that
is what the conflict stage actually writes. ``contradicts`` edges exist in the
schema but have no production writer, so suppressing on them would suppress
nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.read.lineage import LineageQuery, MemoryLineageRepository
from app.read.models import FindSimilarQuery
from app.vectorstore.pgvector_store import PgVectorStore
from tests.integration.conftest import seed_org_agent_memory, with_service_org, zero_embedding
from tests.integration.find_similar_support import (
    InsertScoredMemoryParams,
    build_read_repository,
    insert_scored_memory,
    upsert_embedding,
)

pytestmark = pytest.mark.integration


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def _escalate(
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id: UUID,
    pair: tuple[UUID, UUID],
    status: str = "pending",
) -> UUID:
    new_memory_id, candidate_memory_id = pair
    escalation_id = uuid4()
    async with factory() as session, session.begin():
        await with_service_org(session, org_id)
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                """
                INSERT INTO ibex_core.memory_conflict_escalations (
                    id, org_id, new_memory_id, candidate_memory_id,
                    conflict_type, status, reason
                ) VALUES (
                    :id, :org_id, :new_memory_id, :candidate_memory_id,
                    'contradiction', :status, 'integration test'
                )
                """
            ),
            {
                "id": str(escalation_id),
                "org_id": str(org_id),
                "new_memory_id": str(new_memory_id),
                "candidate_memory_id": str(candidate_memory_id),
                "status": status,
            },
        )
    return escalation_id


async def _seed_pair(
    factory: async_sessionmaker[AsyncSession],
    store: PgVectorStore,
    *,
    org_id: UUID,
    agent_id: UUID,
) -> tuple[UUID, UUID]:
    high = await insert_scored_memory(
        factory,
        InsertScoredMemoryParams(
            org_id=org_id,
            agent_id=agent_id,
            content="the sky is blue",
            category="factual",
            valid_from=_now(),
            confidence=0.95,
        ),
    )
    low = await insert_scored_memory(
        factory,
        InsertScoredMemoryParams(
            org_id=org_id,
            agent_id=agent_id,
            content="the sky is green",
            category="factual",
            valid_from=_now(),
            confidence=0.55,
        ),
    )
    for memory_id in (high, low):
        await upsert_embedding(store, factory, org_id=org_id, memory_id=memory_id, hotspot=0)
    return high, low


def _query(org_id: UUID, agent_id: UUID) -> FindSimilarQuery:
    return FindSimilarQuery(
        org_id=org_id,
        agent_id=agent_id,
        query_embedding=zero_embedding(),
        query_text="sky colour",
        limit=10,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("escalation_status", ["pending", "resolved"])
async def test_only_a_pending_escalation_suppresses(
    session_factory: async_sessionmaker[AsyncSession],
    store: PgVectorStore,
    settings: Settings,
    escalation_status: str,
) -> None:
    expected_suppressed = escalation_status == "pending"
    org_id, agent_id, _root = await seed_org_agent_memory(
        session_factory, content="conflict root"
    )
    high, low = await _seed_pair(
        session_factory, store, org_id=org_id, agent_id=agent_id
    )
    await _escalate(
        session_factory,
        org_id=org_id,
        pair=(high, low),
        status=escalation_status,
    )

    results = await build_read_repository(
        session_factory, store, settings
    ).find_similar(_query(org_id, agent_id))

    returned = {hit.id for hit in results}
    assert high in returned
    assert (low not in returned) is expected_suppressed
    if expected_suppressed:
        assert all(hit.conflict_groups for hit in results if hit.id == high)
    else:
        assert {high, low} <= returned
        assert all(hit.conflict_groups == () for hit in results)


@pytest.mark.asyncio
async def test_superseded_memory_never_enters_the_page(
    session_factory: async_sessionmaker[AsyncSession],
    store: PgVectorStore,
    settings: Settings,
) -> None:
    """Milestone 5.B.2 signal 1, proved rather than assumed.

    Both hydration statements fence ``status = 'active'``, so a superseded
    memory cannot outrank its successor: it is not a candidate at all.
    """
    org_id, agent_id, _root = await seed_org_agent_memory(
        session_factory, content="supersede root"
    )
    successor = await insert_scored_memory(
        session_factory,
        InsertScoredMemoryParams(
            org_id=org_id,
            agent_id=agent_id,
            content="current answer",
            category="factual",
            valid_from=_now(),
            confidence=0.4,
        ),
    )
    superseded = await insert_scored_memory(
        session_factory,
        InsertScoredMemoryParams(
            org_id=org_id,
            agent_id=agent_id,
            content="stale answer",
            category="factual",
            valid_from=_now(),
            confidence=0.99,
            status="superseded",
        ),
    )
    for memory_id in (successor, superseded):
        await upsert_embedding(store, session_factory, org_id=org_id, memory_id=memory_id, hotspot=0)

    results = await build_read_repository(
        session_factory, store, settings
    ).find_similar(_query(org_id, agent_id))

    returned = {hit.id for hit in results}
    assert successor in returned
    assert superseded not in returned


@pytest.mark.asyncio
async def test_lineage_reports_the_pending_conflict_as_an_edge(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Lineage and conflict suppression agree on what a contradiction is."""
    org_id, agent_id, root = await seed_org_agent_memory(
        session_factory, content="lineage conflict root"
    )
    rival = await insert_scored_memory(
        session_factory,
        InsertScoredMemoryParams(
            org_id=org_id,
            agent_id=agent_id,
            content="rival claim",
            category="factual",
            valid_from=_now(),
        ),
    )
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_id)
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                """
                INSERT INTO ibex_core.memory_relationships (
                    org_id, source_memory_id, target_memory_id,
                    relationship_type, confidence
                ) VALUES (:org_id, :source, :target, 'contradicts', 0.8)
                """
            ),
            {"org_id": str(org_id), "source": str(rival), "target": str(root)},
        )

    result = await MemoryLineageRepository(session_factory).get_lineage(
        LineageQuery(org_id=org_id, memory_id=root, max_depth=1)
    )

    assert result is not None
    assert [(edge.relationship_type, edge.other.memory_id) for edge in result.edges] == [
        ("contradicts", rival)
    ]
