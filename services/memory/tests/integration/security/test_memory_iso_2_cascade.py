"""ISO-2.* FK cascade security integration tests (m3.E.1)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.conftest import with_service_org
from tests.integration.security.env import MemorySecurityTestEnv

pytestmark = [pytest.mark.integration, pytest.mark.security_integration]


@pytest.mark.asyncio
async def test_memory_iso_2_1_memory_delete_cascades_fk_children(
    session_factory: async_sessionmaker[AsyncSession],
    security_env: MemorySecurityTestEnv,
) -> None:
    org_a = security_env.orgs.org_a
    target_id = org_a.memory_id
    related_id = await _insert_related_memory(session_factory, org_a.org_id, org_a.agent_id)
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_a.org_id)
        await session.execute(
            text(
                """
                INSERT INTO ibex_core.memory_labels (memory_id, org_id, label, confidence)
                VALUES (:memory_id, :org_id, 'factual', 0.9)
                """
            ),
            {"memory_id": str(target_id), "org_id": str(org_a.org_id)},
        )
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
                "source_id": str(target_id),
                "target_id": str(related_id),
            },
        )
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
                "new_id": str(target_id),
                "candidate_id": str(related_id),
            },
        )
        await session.execute(
            text(
                "DELETE FROM ibex_core.memories WHERE id = :id AND org_id = :org_id"
            ),
            {"id": str(target_id), "org_id": str(org_a.org_id)},
        )
        label_count = (
            await session.execute(
                text(
                    "SELECT COUNT(*)::int AS c FROM ibex_core.memory_labels WHERE memory_id = :id"
                ),
                {"id": str(target_id)},
            )
        ).one()
        rel_count = (
            await session.execute(
                text(
                    """
                    SELECT COUNT(*)::int AS c FROM ibex_core.memory_relationships
                    WHERE source_memory_id = :id OR target_memory_id = :id
                    """
                ),
                {"id": str(target_id)},
            )
        ).one()
        esc_count = (
            await session.execute(
                text(
                    """
                    SELECT COUNT(*)::int AS c
                    FROM ibex_core.memory_conflict_escalations
                    WHERE new_memory_id = :id OR candidate_memory_id = :id
                    """
                ),
                {"id": str(target_id)},
            )
        ).one()
    assert int(label_count.c) == 0
    assert int(rel_count.c) == 0
    assert int(esc_count.c) == 0


async def _insert_related_memory(
    session_factory: async_sessionmaker[AsyncSession],
    org_id,
    agent_id,
):
    from uuid import uuid4

    memory_id = uuid4()
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_id)
        await session.execute(
            text(
                """
                INSERT INTO ibex_core.memories (
                    id, org_id, agent_id, content, content_hash, content_tokens
                ) VALUES (
                    :id, :org_id, :agent_id, :content, :hash, :tokens
                )
                """
            ),
            {
                "id": str(memory_id),
                "org_id": str(org_id),
                "agent_id": str(agent_id),
                "content": "related memory for cascade test",
                "hash": f"hash-{memory_id.hex}",
                "tokens": 5,
            },
        )
    return memory_id
