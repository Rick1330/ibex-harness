"""Real PostgreSQL coverage for provisional lifecycle events during org deletion."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import create_engine, create_session_factory
from app.tasks import org_deletion

pytestmark = pytest.mark.integration


async def _seed_org_memory(
    factory: async_sessionmaker[AsyncSession], *, with_hold: bool
) -> tuple[str, str, str, str]:
    org_id, agent_id, memory_id, job_id = (str(uuid4()) for _ in range(4))
    async with factory() as session, session.begin():
        await session.execute(
            text(
                """INSERT INTO ibex_core.organizations (id, name, slug, status)
                   VALUES (:id, :name, :slug, 'active')"""
            ),
            {"id": org_id, "name": f"Lifecycle purge {org_id[:8]}", "slug": f"life-{org_id[:8]}"},
        )
        await session.execute(
            text(
                """INSERT INTO ibex_core.agents (id, org_id, name, slug)
                   VALUES (:id, :org, 'Lifecycle test agent', :slug)"""
            ),
            {"id": agent_id, "org": org_id, "slug": f"agent-{agent_id[:8]}"},
        )
        await session.execute(
            text(
                """INSERT INTO ibex_core.memories
                   (id, org_id, agent_id, content, content_hash, content_tokens)
                   VALUES (:id, :org, :agent, 'test-only fixture', :hash, 3)"""
            ),
            {"id": memory_id, "org": org_id, "agent": agent_id, "hash": f"hash-{memory_id}"},
        )
        await session.execute(
            text(
                """INSERT INTO ibex_core.org_deletion_jobs (id, org_id, status)
                   VALUES (:id, :org, 'pending')"""
            ),
            {"id": job_id, "org": org_id},
        )
        if with_hold:
            await session.execute(
                text(
                    """INSERT INTO ibex_core.legal_holds (org_id, reason, set_by)
                       VALUES (:org, 'integration hold', :actor)"""
                ),
                {"org": org_id, "actor": str(uuid4())},
            )
    return org_id, agent_id, memory_id, job_id


async def _service_scope(session: AsyncSession, org_id: str) -> None:
    await session.execute(
        text("SELECT set_config('app.current_org_id', :org, true)"), {"org": org_id}
    )
    await session.execute(text("SELECT set_config('app.is_service_account', 'true', true)"))


@pytest.mark.asyncio
async def test_org_postgres_purge_emits_redacted_lifecycle_event(
    migrated_postgres: str,
) -> None:
    engine = create_engine(Settings(database_url=migrated_postgres))
    factory = create_session_factory(engine)
    try:
        org_id, _agent_id, memory_id, _job_id = await _seed_org_memory(factory, with_hold=False)
        async with factory() as session, session.begin():
            await _service_scope(session, org_id)
            await org_deletion._stage_postgres(session, org_id=org_id)
        async with factory() as session:
            event = (
                await session.execute(
                    text(
                        """SELECT revision, event_type FROM ibex_core.memory_lifecycle_outbox
                           WHERE org_id=:org AND memory_id=:memory"""
                    ),
                    {"org": org_id, "memory": memory_id},
                )
            ).one()
            remaining = await session.scalar(
                text("SELECT COUNT(*) FROM ibex_core.memories WHERE id=:memory"),
                {"memory": memory_id},
            )
        assert (int(event.revision), event.event_type) == (2, "purged")
        assert remaining == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_active_legal_hold_defers_org_purge(
    migrated_postgres: str,
) -> None:
    engine = create_engine(Settings(database_url=migrated_postgres))
    factory = create_session_factory(engine)
    try:
        org_id, _agent_id, memory_id, job_id = await _seed_org_memory(factory, with_hold=True)
        async with factory() as session, session.begin():
            await _service_scope(session, org_id)
            result = await org_deletion._finish_if_hold_blocked(
                org_deletion._StageCtx(
                    job_id=job_id,
                    org_id=org_id,
                    settings=Settings(database_url=migrated_postgres),
                    session=session,
                )
            )
        assert result == {"status": "hold_blocked", "job_id": job_id, "org_id": org_id}
        async with factory() as session:
            job_status = (
                await session.execute(
                    text("SELECT status FROM ibex_core.org_deletion_jobs WHERE id=:job"),
                    {"job": job_id},
                )
            ).scalar_one()
            memory_count = await session.scalar(
                text("SELECT COUNT(*) FROM ibex_core.memories WHERE id=:memory"),
                {"memory": memory_id},
            )
            event_count = await session.scalar(
                text(
                    "SELECT COUNT(*) FROM ibex_core.memory_lifecycle_outbox "
                    "WHERE org_id=:org AND memory_id=:memory"
                ),
                {"org": org_id, "memory": memory_id},
            )
        assert job_status == "hold_blocked"
        assert memory_count == 1
        assert event_count == 0
    finally:
        await engine.dispose()
