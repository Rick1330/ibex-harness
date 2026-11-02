"""Integration: deletion evidence is tenant-scoped and the chain check is real.

Two orgs, each with tombstoned records, a receipted erasure job, and a ledger
chain. Org A's chain is broken on purpose, so the continuity check has to say so
while org B's stays intact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import session_with_org
from app.services.operator_evidence_deletions import DeletionArgs, get_evidence_deletions

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)
START = NOW - timedelta(hours=1)


async def _seed_org(session: AsyncSession, org_id: UUID, name: str) -> None:
    await session.execute(
        text(
            "INSERT INTO ibex_core.organizations (id, name, slug) "
            "VALUES (CAST(:id AS uuid), :name, :slug)"
        ),
        {"id": str(org_id), "name": name, "slug": f"deletions-rls-{org_id.hex}"},
    )


async def _seed_agent(session: AsyncSession, org_id: UUID, agent_id: UUID) -> None:
    await session.execute(
        text(
            "INSERT INTO ibex_core.agents (id, org_id, name, slug, status) "
            "VALUES (CAST(:id AS uuid), CAST(:org_id AS uuid), :name, :slug, 'active')"
        ),
        {"id": str(agent_id), "org_id": str(org_id), "name": "A", "slug": f"a-{agent_id.hex}"},
    )


@dataclass(frozen=True)
class SeedMemory:
    org_id: UUID
    agent_id: UUID
    memory_id: UUID
    tombstoned: bool


async def _seed_memory(session: AsyncSession, seed: SeedMemory) -> None:
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.memories (
              id, org_id, agent_id, content, content_hash, content_tokens,
              category, status, confidence, usefulness_score, source,
              retrieval_count, pii_detected, pii_redacted, metadata, tombstoned,
              valid_from, observed_at, created_at, updated_at
            ) VALUES (
              CAST(:id AS uuid), CAST(:org_id AS uuid), CAST(:agent_id AS uuid),
              'body', :content_hash, 1, 'factual', 'active', 0.8, 0.5, 'extracted',
              0, FALSE, FALSE, '{}'::jsonb, :tombstoned,
              :created_at, :created_at, :created_at, :created_at
            )
            """
        ),
        {
            "id": str(seed.memory_id),
            "org_id": str(seed.org_id),
            "agent_id": str(seed.agent_id),
            "content_hash": f"hash-{seed.memory_id.hex}",
            "tombstoned": seed.tombstoned,
            "created_at": START,
        },
    )


@dataclass(frozen=True)
class SeedLifecycleEvent:
    org_id: UUID
    memory_id: UUID
    event_type: str
    delivered: bool


async def _seed_lifecycle_event(session: AsyncSession, seed: SeedLifecycleEvent) -> None:
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.memory_lifecycle_outbox (
              org_id, memory_id, revision, event_type, occurred_at, delivered_at
            ) VALUES (
              CAST(:org_id AS uuid), CAST(:memory_id AS uuid), 1, :event_type,
              :occurred_at, :delivered_at
            )
            """
        ),
        {
            "org_id": str(seed.org_id),
            "memory_id": str(seed.memory_id),
            "event_type": seed.event_type,
            "occurred_at": START,
            "delivered_at": START if seed.delivered else None,
        },
    )


async def _seed_deletion_job(session: AsyncSession, org_id: UUID) -> UUID:
    job_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO ibex_core.org_deletion_jobs (id, org_id, status, created_at) "
            "VALUES (CAST(:id AS uuid), CAST(:org_id AS uuid), 'hold_blocked', :created_at)"
        ),
        {"id": str(job_id), "org_id": str(org_id), "created_at": START},
    )
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.deletion_store_receipts (
              job_id, store, status, verified_absent_at, idempotency_key
            ) VALUES (
              CAST(:job_id AS uuid), 'postgres', 'verified', :at, :key
            )
            """
        ),
        {"job_id": str(job_id), "at": START, "key": f"receipt-{job_id.hex}"},
    )
    return job_id


async def _seed_ledger(
    session: AsyncSession, org_id: UUID, entries: list[tuple[int, str, str]]
) -> None:
    for seq, prev_hash, row_hash in entries:
        await session.execute(
            text(
                """
                INSERT INTO ibex_core.privacy_audit_ledger (
                  org_id, seq, prev_hash, row_hash, action
                ) VALUES (
                  CAST(:org_id AS uuid), :seq, :prev_hash, :row_hash, 'erasure.requested'
                )
                """
            ),
            {
                "org_id": str(org_id),
                "seq": seq,
                "prev_hash": prev_hash,
                "row_hash": row_hash,
            },
        )


async def _cleanup(
    session_factory: async_sessionmaker[AsyncSession], org_a: UUID, org_b: UUID
) -> None:
    targets = {"a": str(org_a), "b": str(org_b)}
    async with session_factory() as cleanup, cleanup.begin():
        # privacy_audit_ledger is append-only on purpose (a trigger rejects
        # UPDATE and DELETE), so its rows survive cleanup; every assertion above
        # is scoped by a fresh org id, so leftovers cannot leak into a later run.
        for statement in (
            (
                "DELETE FROM ibex_core.deletion_store_receipts WHERE job_id IN "
                "(SELECT id FROM ibex_core.org_deletion_jobs "
                "WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid)))"
            ),
            (
                "DELETE FROM ibex_core.org_deletion_jobs "
                "WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
            ),
            (
                "DELETE FROM ibex_core.memory_lifecycle_outbox "
                "WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
            ),
            (
                "DELETE FROM ibex_core.memories "
                "WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
            ),
            (
                "DELETE FROM ibex_core.agents "
                "WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
            ),
            (
                "DELETE FROM ibex_core.organizations "
                "WHERE id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
            ),
        ):
            await cleanup.execute(text(statement), targets)


@dataclass(frozen=True)
class SeedIds:
    org_a: UUID
    org_b: UUID
    agent_a: UUID
    agent_b: UUID


async def _seed_fixture(session_factory: async_sessionmaker[AsyncSession], ids: SeedIds) -> None:
    async with session_factory() as admin, admin.begin():
        await admin.execute(text("SELECT set_config('app.is_service_account', 'true', true)"))
        await _seed_org(admin, ids.org_a, "Deletion Evidence A")
        await _seed_org(admin, ids.org_b, "Deletion Evidence B")
        await _seed_agent(admin, ids.org_a, ids.agent_a)
        await _seed_agent(admin, ids.org_b, ids.agent_b)

        tombstoned_a = uuid4()
        await _seed_memory(admin, SeedMemory(ids.org_a, ids.agent_a, tombstoned_a, True))
        await _seed_memory(admin, SeedMemory(ids.org_a, ids.agent_a, uuid4(), False))
        await _seed_memory(admin, SeedMemory(ids.org_b, ids.agent_b, uuid4(), True))
        await _seed_lifecycle_event(
            admin, SeedLifecycleEvent(ids.org_a, tombstoned_a, "forgotten", False)
        )
        await _seed_deletion_job(admin, ids.org_a)
        await _seed_deletion_job(admin, ids.org_b)
        # Org A: 1 -> 2 is intact, 3 breaks the link.
        genesis = "0" * 64
        await _seed_ledger(
            admin,
            ids.org_a,
            [(1, genesis, "hash-1"), (2, "hash-1", "hash-2"), (3, "hash-x", "hash-3")],
        )
        await _seed_ledger(admin, ids.org_b, [(1, genesis, "hash-1"), (2, "hash-1", "hash-2")])


@pytest.mark.asyncio
async def test_deletion_evidence_is_tenant_scoped_and_flags_a_broken_chain(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ids = SeedIds(org_a=uuid4(), org_b=uuid4(), agent_a=uuid4(), agent_b=uuid4())
    try:
        await _seed_fixture(session_factory, ids)

        async with session_with_org(session_factory, str(ids.org_a)) as session:
            a = await get_evidence_deletions(
                session, DeletionArgs(org_id=ids.org_a, range="24h"), now=NOW
            )
        async with session_with_org(session_factory, str(ids.org_b)) as session:
            b = await get_evidence_deletions(
                session, DeletionArgs(org_id=ids.org_b, range="24h"), now=NOW
            )

        assert a.tombstones.events.forgotten == 1
        assert a.tombstones.pending == 1
        assert a.tombstones.tombstoned_memories == 1
        assert a.erasures.hold_blocked == 1
        assert len(a.jobs) == 1
        assert [(r.store, r.status) for r in a.jobs[0].receipts] == [("postgres", "verified")]
        assert a.audit.entries == 3
        assert a.audit.continuity_ok is False
        assert a.audit.broken_at_seq == 3

        assert b.tombstones.events.forgotten == 0
        assert b.tombstones.tombstoned_memories == 1
        assert b.erasures.hold_blocked == 1
        assert b.audit.entries == 2
        assert b.audit.continuity_ok is True
        assert b.audit.broken_at_seq is None
    finally:
        await _cleanup(session_factory, ids.org_a, ids.org_b)
