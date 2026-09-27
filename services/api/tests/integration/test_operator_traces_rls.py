"""Integration: D2 operator trace reads honor org GUC, RLS, and anti-enumeration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from apierror_py import NOT_FOUND
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import create_engine, create_session_factory, session_with_org
from app.errors import ApiError
from app.operator_session_auth import OperatorSessionAuthorization
from app.schemas.operator_traces import OperatorTraceListQuery
from app.services.operator_traces import get_operator_trace_run, list_operator_traces

pytestmark = pytest.mark.integration

CURSOR_SECRET = "cursor-secret-32-bytes-minimum!!"
START = datetime(2026, 9, 27, 8, tzinfo=UTC)
END = START + timedelta(hours=1)


def _require_dsn() -> str:
    dsn = os.environ.get("IBEX_API_DATABASE_URL") or os.environ.get("POSTGRES_TEST_DSN")
    if not dsn:
        pytest.skip("IBEX_API_DATABASE_URL or POSTGRES_TEST_DSN not set")
    return dsn


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_engine(Settings(database_url=_require_dsn(), operator_cursor_secret=CURSOR_SECRET))
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


def _settings() -> Settings:
    return Settings(database_url=_require_dsn(), operator_cursor_secret=CURSOR_SECRET)


def _auth(org_id: UUID) -> OperatorSessionAuthorization:
    return OperatorSessionAuthorization(org_id=org_id, permissions=1, session_id="s", subject="u")


async def _seed_org(session: AsyncSession, org_id: UUID, name: str) -> None:
    await session.execute(
        text(
            "INSERT INTO ibex_core.organizations (id, name, slug) "
            "VALUES (CAST(:id AS uuid), :name, :slug)"
        ),
        {"id": str(org_id), "name": name, "slug": f"d2-rls-{org_id.hex}"},
    )


@dataclass(frozen=True)
class SeedRun:
    org_id: UUID
    run_id: UUID
    trace_id: str
    request_id: str
    status: str = "ok"


@dataclass(frozen=True)
class SeedOutbox:
    org_id: UUID
    request_id: str
    delivery_status: str = "delivered"
    seq: int = 1


async def _seed_run(session: AsyncSession, seed: SeedRun) -> None:
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.evidence_runs (
              id, org_id, request_id, trace_id, schema_version, completeness,
              status, capture_mode, sample_decision, started_at, ended_at
            ) VALUES (
              CAST(:id AS uuid), CAST(:org_id AS uuid), :request_id, :trace_id,
              'evidence.v1', 'partial', :status, 'metadata', 'kept', :started_at, :ended_at
            )
            """
        ),
        {
            "id": str(seed.run_id),
            "org_id": str(seed.org_id),
            "request_id": seed.request_id,
            "trace_id": seed.trace_id,
            "status": seed.status,
            "started_at": START,
            "ended_at": END,
        },
    )


async def _seed_outbox(session: AsyncSession, seed: SeedOutbox) -> None:
    delivered_at = END if seed.delivery_status == "delivered" else None
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.evidence_outbox (
              id, org_id, event_id, aggregate_id, aggregate_seq, schema_version,
              event_type, payload, payload_digest, delivery_status, delivered_at
            ) VALUES (
              gen_random_uuid(), CAST(:org_id AS uuid), gen_random_uuid(), :aggregate_id, :seq,
              'evidence.v1', 'run.persisted', '{}'::jsonb, 'digest', :status,
              CAST(:delivered_at AS timestamptz)
            )
            """
        ),
        {
            "org_id": str(seed.org_id),
            "aggregate_id": seed.request_id,
            "seq": seed.seq,
            "status": seed.delivery_status,
            "delivered_at": delivered_at,
        },
    )


async def _cleanup(session_factory: async_sessionmaker[AsyncSession], org_a: UUID, org_b: UUID) -> None:
    async with session_factory() as cleanup, cleanup.begin():
        await cleanup.execute(
            text(
                "DELETE FROM ibex_core.evidence_outbox "
                "WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
            ),
            {"a": str(org_a), "b": str(org_b)},
        )
        await cleanup.execute(
            text(
                "DELETE FROM ibex_core.evidence_runs "
                "WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
            ),
            {"a": str(org_a), "b": str(org_b)},
        )
        await cleanup.execute(
            text("DELETE FROM ibex_core.organizations WHERE id IN (CAST(:a AS uuid), CAST(:b AS uuid))"),
            {"a": str(org_a), "b": str(org_b)},
        )


@pytest.mark.asyncio
async def test_operator_traces_are_tenant_scoped_with_publication_and_404_boundary(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_a = uuid4()
    org_b = uuid4()
    run_a = uuid4()
    run_b = uuid4()
    try:
        async with session_factory() as admin, admin.begin():
            await admin.execute(text("SELECT set_config('app.is_service_account', 'true', true)"))
            await _seed_org(admin, org_a, "D2 RLS A")
            await _seed_org(admin, org_b, "D2 RLS B")
            await _seed_run(admin, SeedRun(org_a, run_a, "trace-a", "req-a"))
            await _seed_run(admin, SeedRun(org_b, run_b, "trace-b", "req-b"))
            await _seed_outbox(admin, SeedOutbox(org_a, "req-a", delivery_status="delivered", seq=3))
            await _seed_outbox(admin, SeedOutbox(org_b, "req-b", delivery_status="pending", seq=1))

        settings = _settings()
        async with session_with_org(session_factory, org_a) as session:
            listed = await list_operator_traces(
                session,
                settings,
                _auth(org_a),
                OperatorTraceListQuery(
                    started_after=START - timedelta(hours=1),
                    started_before=END + timedelta(hours=1),
                    limit=50,
                ),
            )
            assert listed.returned_count == 1
            assert listed.items[0].run_id == run_a
            assert listed.items[0].evidence.publication_state == "published"
            assert listed.items[0].evidence.source_watermark == "outbox:3"

            detail = await get_operator_trace_run(session, _auth(org_a), run_id=run_a)
            assert detail.run_id == run_a
            assert "content" in detail.unavailable_sections

            with pytest.raises(ApiError) as err:
                await get_operator_trace_run(session, _auth(org_a), run_id=run_b)
            assert err.value.code == NOT_FOUND

        async with session_with_org(session_factory, org_b) as session:
            listed_b = await list_operator_traces(
                session,
                settings,
                _auth(org_b),
                OperatorTraceListQuery(
                    started_after=START - timedelta(hours=1),
                    started_before=END + timedelta(hours=1),
                    limit=50,
                ),
            )
            assert listed_b.returned_count == 1
            assert listed_b.items[0].run_id == run_b
            assert listed_b.items[0].evidence.publication_state == "pending"
    finally:
        await _cleanup(session_factory, org_a, org_b)
