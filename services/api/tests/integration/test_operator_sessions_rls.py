"""Integration: metadata-only operator session reads honor scope and the turn join."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from apierror_py import NOT_FOUND
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import session_with_org
from app.errors import ApiError
from app.services.operator_sessions import (
    ListSessionsArgs,
    SessionListFilters,
    get_operator_session,
    list_operator_sessions,
)

pytestmark = pytest.mark.integration

START = datetime(2026, 11, 2, 8, tzinfo=UTC)


@dataclass(frozen=True)
class SeedSession:
    org_id: UUID
    agent_id: UUID
    session_id: UUID
    status: str = "active"
    created_at: datetime = START
    deleted: bool = False


async def _seed_org(session: AsyncSession, org_id: UUID, name: str) -> None:
    await session.execute(
        text(
            "INSERT INTO ibex_core.organizations (id, name, slug) "
            "VALUES (CAST(:id AS uuid), :name, :slug)"
        ),
        {"id": str(org_id), "name": name, "slug": f"sess-rls-{org_id.hex}"},
    )


async def _seed_agent(
    session: AsyncSession, org_id: UUID, agent_id: UUID, name: str
) -> None:
    await session.execute(
        text(
            "INSERT INTO ibex_core.agents (id, org_id, name, slug, status) "
            "VALUES (CAST(:id AS uuid), CAST(:org_id AS uuid), :name, :slug, 'active')"
        ),
        {
            "id": str(agent_id),
            "org_id": str(org_id),
            "name": name,
            "slug": f"sess-rls-{agent_id.hex}",
        },
    )


async def _seed_session(session: AsyncSession, seed: SeedSession) -> None:
    completed_at = seed.created_at if seed.status == "completed" else None
    deleted_at = seed.created_at if seed.deleted else None
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.sessions (
              id, org_id, agent_id, external_id, status, model, provider,
              turn_count, total_input_tokens, total_output_tokens, total_latency_ms,
              last_extracted_turn, created_at, updated_at, completed_at, deleted_at
            ) VALUES (
              CAST(:id AS uuid), CAST(:org_id AS uuid), CAST(:agent_id AS uuid),
              :external_id, :status, 'gpt-4.1', 'openai',
              2, 100, 50, 1200, 1, :created_at, :created_at,
              :completed_at, :deleted_at
            )
            """
        ),
        {
            "id": str(seed.session_id),
            "org_id": str(seed.org_id),
            "agent_id": str(seed.agent_id),
            "external_id": f"ext-{seed.session_id.hex}",
            "status": seed.status,
            "created_at": seed.created_at,
            "completed_at": completed_at,
            "deleted_at": deleted_at,
        },
    )


@dataclass(frozen=True)
class SeedCheckpoint:
    org_id: UUID
    agent_id: UUID
    session_id: UUID
    checkpoint_id: UUID
    turn_index: int
    request_id: str


async def _seed_checkpoint(session: AsyncSession, seed: SeedCheckpoint) -> None:
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.checkpoints (
              id, session_id, org_id, agent_id, turn_index, request_id,
              messages_hash, input_tokens, output_tokens, model, provider,
              latency_ms, is_streaming, is_complete, created_at
            ) VALUES (
              CAST(:id AS uuid), CAST(:session_id AS uuid), CAST(:org_id AS uuid),
              CAST(:agent_id AS uuid), :turn_index, :request_id,
              :messages_hash, 10, 20, 'gpt-4.1', 'openai',
              100, FALSE, TRUE, :created_at
            )
            """
        ),
        {
            "id": str(seed.checkpoint_id),
            "session_id": str(seed.session_id),
            "org_id": str(seed.org_id),
            "agent_id": str(seed.agent_id),
            "turn_index": seed.turn_index,
            "request_id": seed.request_id,
            "messages_hash": f"hash-{seed.checkpoint_id.hex}",
            "created_at": START,
        },
    )


@dataclass(frozen=True)
class SeedEvidence:
    org_id: UUID
    agent_id: UUID
    session_id: UUID
    checkpoint_id: UUID
    run_id: UUID
    request_id: str
    trace_id: str
    status: str
    started_at: datetime


async def _seed_evidence(session: AsyncSession, seed: SeedEvidence) -> None:
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.evidence_runs (
              id, org_id, agent_id, session_id, request_id, trace_id,
              checkpoint_id, turn_id, schema_version, completeness, status,
              error_code, capture_mode, sample_decision, started_at, ended_at
            ) VALUES (
              CAST(:id AS uuid), CAST(:org_id AS uuid), CAST(:agent_id AS uuid),
              CAST(:session_id AS uuid), :request_id, :trace_id,
              CAST(:checkpoint_id AS uuid), 0, 'evidence.v1', 'complete', :status,
              :error_code, 'metadata', 'sampled', :started_at, :started_at
            )
            """
        ),
        {
            "id": str(seed.run_id),
            "org_id": str(seed.org_id),
            "agent_id": str(seed.agent_id),
            "session_id": str(seed.session_id),
            "request_id": seed.request_id,
            "trace_id": seed.trace_id,
            "checkpoint_id": str(seed.checkpoint_id),
            "status": seed.status,
            "error_code": "provider_timeout" if seed.status != "ok" else None,
            "started_at": seed.started_at,
        },
    )


async def _cleanup(
    session_factory: async_sessionmaker[AsyncSession], org_a: UUID, org_b: UUID
) -> None:
    targets = {"a": str(org_a), "b": str(org_b)}
    async with session_factory() as cleanup, cleanup.begin():
        for statement in (
            (
                "DELETE FROM ibex_core.evidence_runs "
                "WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
            ),
            (
                "DELETE FROM ibex_core.checkpoints "
                "WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
            ),
            (
                "DELETE FROM ibex_core.sessions "
                "WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
            ),
            (
                "DELETE FROM ibex_core.agents "
                "WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
            ),
        ):
            await cleanup.execute(text(statement), targets)
        await cleanup.execute(
            text(
                "DELETE FROM ibex_core.organizations "
                "WHERE id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
            ),
            targets,
        )


@dataclass(frozen=True)
class SeedIds:
    org_a: UUID
    org_b: UUID
    agent_a: UUID
    agent_b: UUID
    session_a1: UUID
    session_a2: UUID
    session_deleted: UUID
    session_b: UUID
    checkpoint_0: UUID
    checkpoint_1: UUID


async def _seed_tenants(admin: AsyncSession, ids: SeedIds) -> None:
    await _seed_org(admin, ids.org_a, "Session RLS A")
    await _seed_org(admin, ids.org_b, "Session RLS B")
    await _seed_agent(admin, ids.org_a, ids.agent_a, "Agent A")
    await _seed_agent(admin, ids.org_b, ids.agent_b, "Agent B")
    await _seed_session(admin, SeedSession(ids.org_a, ids.agent_a, ids.session_a1))
    await _seed_session(
        admin,
        SeedSession(
            ids.org_a,
            ids.agent_a,
            ids.session_a2,
            status="completed",
            created_at=START + timedelta(minutes=1),
        ),
    )
    await _seed_session(
        admin,
        SeedSession(
            ids.org_a,
            ids.agent_a,
            ids.session_deleted,
            created_at=START + timedelta(minutes=2),
            deleted=True,
        ),
    )
    await _seed_session(
        admin, SeedSession(ids.org_b, ids.agent_b, ids.session_b, status="error")
    )


async def _seed_turns(admin: AsyncSession, ids: SeedIds) -> None:
    await _seed_checkpoint(
        admin,
        SeedCheckpoint(
            ids.org_a, ids.agent_a, ids.session_a1, ids.checkpoint_0, 0, "req-a1-0"
        ),
    )
    await _seed_checkpoint(
        admin,
        SeedCheckpoint(
            ids.org_a, ids.agent_a, ids.session_a1, ids.checkpoint_1, 1, "req-a1-1"
        ),
    )
    await _seed_evidence(
        admin,
        SeedEvidence(
            ids.org_a,
            ids.agent_a,
            ids.session_a1,
            ids.checkpoint_0,
            uuid4(),
            "run-a1-0-old",
            "trace-old",
            "ok",
            START,
        ),
    )
    await _seed_evidence(
        admin,
        SeedEvidence(
            ids.org_a,
            ids.agent_a,
            ids.session_a1,
            ids.checkpoint_0,
            uuid4(),
            "run-a1-0-new",
            "trace-new",
            "error",
            START + timedelta(minutes=1),
        ),
    )


async def _seed_fixture(
    session_factory: async_sessionmaker[AsyncSession], ids: SeedIds
) -> None:
    async with session_factory() as admin, admin.begin():
        await admin.execute(
            text("SELECT set_config('app.is_service_account', 'true', true)")
        )
        await _seed_tenants(admin, ids)
        await _seed_turns(admin, ids)


async def _assert_list(session: AsyncSession, ids: SeedIds) -> None:
    listed = await list_operator_sessions(
        session,
        ListSessionsArgs(
            org_id=ids.org_a, cursor=None, limit=50, filters=SessionListFilters()
        ),
    )
    assert [item.id for item in listed.data] == [ids.session_a2, ids.session_a1]
    dumped = listed.data[0].model_dump()
    assert "org_id" not in dumped
    assert "deleted_at" not in dumped

    completed = await list_operator_sessions(
        session,
        ListSessionsArgs(
            org_id=ids.org_a,
            cursor=None,
            limit=50,
            filters=SessionListFilters(status="completed"),
        ),
    )
    assert [item.id for item in completed.data] == [ids.session_a2]

    by_agent = await list_operator_sessions(
        session,
        ListSessionsArgs(
            org_id=ids.org_a,
            cursor=None,
            limit=50,
            filters=SessionListFilters(agent_id=ids.agent_a),
        ),
    )
    assert [item.id for item in by_agent.data] == [ids.session_a2, ids.session_a1]


async def _assert_cursor(session: AsyncSession, ids: SeedIds) -> None:
    first = await list_operator_sessions(
        session,
        ListSessionsArgs(
            org_id=ids.org_a, cursor=None, limit=1, filters=SessionListFilters()
        ),
    )
    assert first.pagination.has_more is True
    assert first.pagination.next_cursor is not None
    second = await list_operator_sessions(
        session,
        ListSessionsArgs(
            org_id=ids.org_a,
            cursor=first.pagination.next_cursor,
            limit=1,
            filters=SessionListFilters(),
        ),
    )
    assert [item.id for item in second.data] == [ids.session_a1]


async def _assert_detail(session: AsyncSession, ids: SeedIds) -> None:
    detail = await get_operator_session(session, ids.org_a, ids.session_a1)
    assert detail.id == ids.session_a1
    assert [turn.turn_index for turn in detail.turns] == [0, 1]
    assert detail.turns[0].trace is not None
    assert detail.turns[0].trace.trace_id == "trace-new"
    assert detail.turns[0].trace.status == "error"
    assert detail.turns[0].trace.error_code == "provider_timeout"
    assert detail.turns[1].trace is None
    assert detail.turns_truncated is False
    dumped = detail.model_dump()
    assert "messages_hash" not in dumped
    assert "org_id" not in dumped

    for target in (uuid4(), ids.session_b, ids.session_deleted):
        with pytest.raises(ApiError) as err:
            await get_operator_session(session, ids.org_a, target)
        assert err.value.code == NOT_FOUND


@pytest.mark.asyncio
async def test_operator_sessions_are_tenant_scoped_and_join_turns(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ids = SeedIds(
        org_a=uuid4(),
        org_b=uuid4(),
        agent_a=uuid4(),
        agent_b=uuid4(),
        session_a1=uuid4(),
        session_a2=uuid4(),
        session_deleted=uuid4(),
        session_b=uuid4(),
        checkpoint_0=uuid4(),
        checkpoint_1=uuid4(),
    )
    try:
        await _seed_fixture(session_factory, ids)
        async with session_with_org(session_factory, str(ids.org_a)) as session:
            await _assert_list(session, ids)
            await _assert_cursor(session, ids)
            await _assert_detail(session, ids)
        async with session_with_org(session_factory, str(ids.org_b)) as session:
            other = await list_operator_sessions(
                session,
                ListSessionsArgs(
                    org_id=ids.org_b,
                    cursor=None,
                    limit=50,
                    filters=SessionListFilters(),
                ),
            )
            assert [item.id for item in other.data] == [ids.session_b]
    finally:
        await _cleanup(session_factory, ids.org_a, ids.org_b)
