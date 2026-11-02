"""Integration: the operator evidence summary honors tenant scope.

The service filters `org_id` explicitly, in addition to RLS, so this test proves
the read model cannot see another tenant even when it is asked for it directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import session_with_org
from app.services.operator_evidence import EvidenceSummaryArgs, get_evidence_summary

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)
START = NOW - timedelta(hours=1)


async def _seed_org(session: AsyncSession, org_id: UUID, name: str) -> None:
    await session.execute(
        text(
            "INSERT INTO ibex_core.organizations (id, name, slug) "
            "VALUES (CAST(:id AS uuid), :name, :slug)"
        ),
        {"id": str(org_id), "name": name, "slug": f"evidence-rls-{org_id.hex}"},
    )


@dataclass(frozen=True)
class SeedRun:
    org_id: UUID
    run_id: UUID
    request_id: str
    completeness: str
    status: str
    started_at: datetime = START


async def _seed_run(session: AsyncSession, seed: SeedRun) -> None:
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.evidence_runs (
              id, org_id, request_id, trace_id, schema_version, completeness,
              status, capture_mode, sample_decision, started_at, ended_at
            ) VALUES (
              CAST(:id AS uuid), CAST(:org_id AS uuid), :request_id, :trace_id,
              'evidence.v1', :completeness, :status, 'metadata', 'sampled',
              :started_at, :started_at
            )
            """
        ),
        {
            "id": str(seed.run_id),
            "org_id": str(seed.org_id),
            "request_id": seed.request_id,
            "trace_id": f"trace-{seed.run_id.hex}",
            "completeness": seed.completeness,
            "status": seed.status,
            "started_at": seed.started_at,
        },
    )


@dataclass(frozen=True)
class SeedOutbox:
    org_id: UUID
    event_id: UUID
    aggregate_id: str
    seq: int
    delivery_status: str
    created_at: datetime = START


async def _seed_outbox(session: AsyncSession, seed: SeedOutbox) -> None:
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.evidence_outbox (
              org_id, event_id, aggregate_id, aggregate_seq, schema_version,
              event_type, payload, payload_digest, delivery_status, created_at
            ) VALUES (
              CAST(:org_id AS uuid), CAST(:event_id AS uuid), :aggregate_id, :seq,
              'evidence.v1', 'memory.written', '{}'::jsonb, :digest,
              :delivery_status, :created_at
            )
            """
        ),
        {
            "org_id": str(seed.org_id),
            "event_id": str(seed.event_id),
            "aggregate_id": seed.aggregate_id,
            "seq": seed.seq,
            "digest": f"digest-{seed.event_id.hex}",
            "delivery_status": seed.delivery_status,
            "created_at": seed.created_at,
        },
    )


async def _seed_capture_policy(session: AsyncSession, org_id: UUID, mode: str) -> None:
    await session.execute(
        text(
            "INSERT INTO ibex_core.org_capture_policies (org_id, mode, priority) "
            "VALUES (CAST(:org_id AS uuid), :mode, 100)"
        ),
        {"org_id": str(org_id), "mode": mode},
    )


async def _seed_legal_hold(session: AsyncSession, org_id: UUID) -> None:
    await session.execute(
        text(
            "INSERT INTO ibex_core.legal_holds (org_id, scope, reason, set_by) "
            "VALUES (CAST(:org_id AS uuid), 'org', 'litigation hold', CAST(:actor AS uuid))"
        ),
        {"org_id": str(org_id), "actor": str(uuid4())},
    )


async def _cleanup(
    session_factory: async_sessionmaker[AsyncSession], org_a: UUID, org_b: UUID
) -> None:
    targets = {"a": str(org_a), "b": str(org_b)}
    async with session_factory() as cleanup, cleanup.begin():
        for statement in (
            "DELETE FROM ibex_core.evidence_runs WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))",
            "DELETE FROM ibex_core.evidence_outbox WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))",
            "DELETE FROM ibex_core.legal_holds WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))",
            (
                "DELETE FROM ibex_core.org_capture_policies "
                "WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
            ),
            "DELETE FROM ibex_core.organizations WHERE id IN (CAST(:a AS uuid), CAST(:b AS uuid))",
        ):
            await cleanup.execute(text(statement), targets)


@dataclass(frozen=True)
class SeedIds:
    org_a: UUID
    org_b: UUID


async def _seed_fixture(session_factory: async_sessionmaker[AsyncSession], ids: SeedIds) -> None:
    async with session_factory() as admin, admin.begin():
        await admin.execute(text("SELECT set_config('app.is_service_account', 'true', true)"))
        await _seed_org(admin, ids.org_a, "Evidence RLS A")
        await _seed_org(admin, ids.org_b, "Evidence RLS B")

        await _seed_run(
            admin, SeedRun(ids.org_a, uuid4(), "req-a-1", "complete", "ok")
        )
        await _seed_run(
            admin, SeedRun(ids.org_a, uuid4(), "req-a-2", "complete", "ok")
        )
        await _seed_run(
            admin, SeedRun(ids.org_a, uuid4(), "req-a-3", "partial", "error")
        )
        await _seed_run(
            admin, SeedRun(ids.org_b, uuid4(), "req-b-1", "sampled", "ok")
        )

        await _seed_outbox(
            admin, SeedOutbox(ids.org_a, uuid4(), "agg-a", 1, "delivered")
        )
        await _seed_outbox(admin, SeedOutbox(ids.org_a, uuid4(), "agg-a", 2, "pending"))
        await _seed_outbox(admin, SeedOutbox(ids.org_b, uuid4(), "agg-b", 1, "poison"))

        await _seed_capture_policy(admin, ids.org_a, "metadata_only")
        await _seed_legal_hold(admin, ids.org_a)


@pytest.mark.asyncio
async def test_evidence_summary_is_tenant_scoped(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ids = SeedIds(org_a=uuid4(), org_b=uuid4())
    try:
        await _seed_fixture(session_factory, ids)

        async with session_with_org(session_factory, str(ids.org_a)) as session:
            summary = await get_evidence_summary(
                session, EvidenceSummaryArgs(org_id=ids.org_a, range="24h")
            )

        assert summary.runs_total == 3
        assert summary.capture_complete_runs == 2
        assert summary.completeness.complete == 2
        assert summary.completeness.partial == 1
        assert summary.completeness.sampled == 0
        assert summary.statuses.ok == 2
        assert summary.statuses.error == 1
        assert summary.delivery.delivered == 1
        assert summary.delivery.pending == 1
        assert summary.delivery.poison == 0
        assert summary.capture_policy.mode == "metadata_only"
        assert summary.legal_hold.active is True

        async with session_with_org(session_factory, str(ids.org_b)) as session:
            other = await get_evidence_summary(
                session, EvidenceSummaryArgs(org_id=ids.org_b, range="24h")
            )

        assert other.runs_total == 1
        assert other.completeness.sampled == 1
        assert other.delivery.poison == 1
        assert other.delivery.pending == 0
        assert other.capture_policy.mode is None
        assert other.legal_hold.active is False
    finally:
        await _cleanup(session_factory, ids.org_a, ids.org_b)


@pytest.mark.asyncio
async def test_evidence_summary_ignores_runs_outside_the_window(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ids = SeedIds(org_a=uuid4(), org_b=uuid4())
    try:
        await _seed_fixture(session_factory, ids)
        async with session_factory() as admin, admin.begin():
            await admin.execute(
                text(
                    """
                    INSERT INTO ibex_core.evidence_runs (
                      id, org_id, request_id, trace_id, schema_version, completeness,
                      status, capture_mode, sample_decision, started_at
                    ) VALUES (
                      CAST(:id AS uuid), CAST(:org_id AS uuid), 'req-a-old', :trace_id,
                      'evidence.v1', 'complete', 'ok', 'metadata', 'sampled',
                      :started_at
                    )
                    """
                ),
                {
                    "id": str(uuid4()),
                    "org_id": str(ids.org_a),
                    "trace_id": f"trace-old-{uuid4().hex}",
                    "started_at": NOW - timedelta(days=40),
                },
            )

        async with session_with_org(session_factory, str(ids.org_a)) as session:
            summary = await get_evidence_summary(
                session, EvidenceSummaryArgs(org_id=ids.org_a, range="24h")
            )

        assert summary.runs_total == 3
        assert summary.completeness.complete == 2
    finally:
        await _cleanup(session_factory, ids.org_a, ids.org_b)
