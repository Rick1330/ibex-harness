"""Integration: directive reads honor tenant scope and the live pointer.

The list and detail both filter `org_id` explicitly, in addition to RLS, so this
proves the read model cannot see another tenant even when asked directly. It also
proves the pointer rule: a rollback leaves the newest version newest and the live
version live.
"""

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
from app.services.operator_directives import (
    DirectiveDetailArgs,
    DirectiveListArgs,
    get_operator_directive,
    list_operator_directives,
)

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)
START = NOW - timedelta(hours=1)


async def _seed_org(session: AsyncSession, org_id: UUID, name: str) -> None:
    await session.execute(
        text(
            "INSERT INTO ibex_core.organizations (id, name, slug) "
            "VALUES (CAST(:id AS uuid), :name, :slug)"
        ),
        {"id": str(org_id), "name": name, "slug": f"directive-rls-{org_id.hex}"},
    )


async def _seed_agent(session: AsyncSession, org_id: UUID, agent_id: UUID, name: str) -> None:
    await session.execute(
        text(
            "INSERT INTO ibex_core.agents (id, org_id, name, slug, status) "
            "VALUES (CAST(:id AS uuid), CAST(:org_id AS uuid), :name, :slug, 'active')"
        ),
        {"id": str(agent_id), "org_id": str(org_id), "name": name, "slug": f"d-{agent_id.hex}"},
    )


async def _seed_directive(
    session: AsyncSession, org_id: UUID, agent_id: UUID, directive_id: UUID
) -> None:
    await session.execute(
        text(
            "INSERT INTO ibex_core.directives (id, org_id, agent_id, injection_mode, is_active) "
            "VALUES (CAST(:id AS uuid), CAST(:org_id AS uuid), CAST(:agent_id AS uuid), "
            "'system_first', TRUE)"
        ),
        {"id": str(directive_id), "org_id": str(org_id), "agent_id": str(agent_id)},
    )


@dataclass(frozen=True)
class SeedVersion:
    org_id: UUID
    directive_id: UUID
    version_id: UUID
    version_num: int
    created_at: datetime = START


async def _seed_version(session: AsyncSession, seed: SeedVersion) -> None:
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.directive_versions (
              id, directive_id, org_id, version_num, content, content_hash, created_at
            ) VALUES (
              CAST(:id AS uuid), CAST(:directive_id AS uuid), CAST(:org_id AS uuid),
              :version_num, :content, :content_hash, :created_at
            )
            """
        ),
        {
            "id": str(seed.version_id),
            "directive_id": str(seed.directive_id),
            "org_id": str(seed.org_id),
            "version_num": seed.version_num,
            "content": f"instruction text for version {seed.version_num}",
            "content_hash": "a" * 64 if seed.version_num == 1 else "b" * 64,
            "created_at": seed.created_at,
        },
    )


async def _point_at(session: AsyncSession, directive_id: UUID, version_id: UUID) -> None:
    await session.execute(
        text(
            "UPDATE ibex_core.directives SET active_version_id = CAST(:version_id AS uuid) "
            "WHERE id = CAST(:directive_id AS uuid)"
        ),
        {"directive_id": str(directive_id), "version_id": str(version_id)},
    )


@dataclass(frozen=True)
class SeedSession:
    org_id: UUID
    agent_id: UUID
    version_id: UUID


async def _seed_session(session: AsyncSession, seed: SeedSession) -> None:
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.sessions (
              org_id, agent_id, status, model, provider, directive_version_id,
              turn_count, total_input_tokens, total_output_tokens, total_latency_ms,
              last_extracted_turn, created_at, updated_at
            ) VALUES (
              CAST(:org_id AS uuid), CAST(:agent_id AS uuid), 'active', 'gpt-4.1', 'openai',
              CAST(:version_id AS uuid), 0, 0, 0, 0, 0, :created_at, :created_at
            )
            """
        ),
        {
            "org_id": str(seed.org_id),
            "agent_id": str(seed.agent_id),
            "version_id": str(seed.version_id),
            "created_at": START,
        },
    )


async def _cleanup(
    session_factory: async_sessionmaker[AsyncSession], org_a: UUID, org_b: UUID
) -> None:
    targets = {"a": str(org_a), "b": str(org_b)}
    async with session_factory() as cleanup, cleanup.begin():
        for statement in (
            "DELETE FROM ibex_core.sessions WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))",
            (
                "DELETE FROM ibex_core.directive_versions "
                "WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
            ),
            (
                "DELETE FROM ibex_core.directives "
                "WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
            ),
            "DELETE FROM ibex_core.agents WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))",
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
    directive_a: UUID
    directive_b: UUID
    version_a1: UUID
    version_a2: UUID
    version_b1: UUID


async def _seed_fixture(session_factory: async_sessionmaker[AsyncSession], ids: SeedIds) -> None:
    async with session_factory() as admin, admin.begin():
        await admin.execute(text("SELECT set_config('app.is_service_account', 'true', true)"))
        await _seed_org(admin, ids.org_a, "Directive RLS A")
        await _seed_org(admin, ids.org_b, "Directive RLS B")
        await _seed_agent(admin, ids.org_a, ids.agent_a, "Agent A")
        await _seed_agent(admin, ids.org_b, ids.agent_b, "Agent B")
        await _seed_directive(admin, ids.org_a, ids.agent_a, ids.directive_a)
        await _seed_directive(admin, ids.org_b, ids.agent_b, ids.directive_b)
        await _seed_version(
            admin, SeedVersion(ids.org_a, ids.directive_a, ids.version_a1, 1)
        )
        await _seed_version(
            admin,
            SeedVersion(
                ids.org_a,
                ids.directive_a,
                ids.version_a2,
                2,
                created_at=START + timedelta(minutes=5),
            ),
        )
        await _seed_version(
            admin, SeedVersion(ids.org_b, ids.directive_b, ids.version_b1, 1)
        )
        # Rollback: the pointer names v1 while v2 is the newest version.
        await _point_at(admin, ids.directive_a, ids.version_a1)
        await _seed_session(
            admin, SeedSession(ids.org_a, ids.agent_a, ids.version_a1)
        )
        await _seed_session(
            admin, SeedSession(ids.org_a, ids.agent_a, ids.version_a1)
        )


@pytest.mark.asyncio
async def test_directive_reads_are_tenant_scoped_and_follow_the_pointer(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ids = SeedIds(
        org_a=uuid4(),
        org_b=uuid4(),
        agent_a=uuid4(),
        agent_b=uuid4(),
        directive_a=uuid4(),
        directive_b=uuid4(),
        version_a1=uuid4(),
        version_a2=uuid4(),
        version_b1=uuid4(),
    )
    try:
        await _seed_fixture(session_factory, ids)

        async with session_with_org(session_factory, str(ids.org_a)) as session:
            page = await list_operator_directives(
                session,
                DirectiveListArgs(
                    org_id=ids.org_a, state="all", agent_id=None, cursor=None, limit=50
                ),
            )
            detail = await get_operator_directive(
                session,
                DirectiveDetailArgs(
                    org_id=ids.org_a, directive_id=ids.directive_a, usage_range="24h"
                ),
                now=NOW,
            )

        assert [row.id for row in page.data] == [ids.directive_a]
        assert page.observed_at is not None
        assert page.data[0].version_count == 2
        # v1 is live after the rollback even though v2 is the newest version.
        assert page.data[0].active_version_num == 1
        assert [version.version_num for version in detail.versions] == [2, 1]
        assert [version.is_live for version in detail.versions] == [False, True]
        assert [(row.version_num, row.sessions) for row in detail.usage] == [(1, 2)]
        assert detail.active_version_missing is False
        assert detail.version_count == 2
        assert detail.versions_truncated is False
        assert detail.observed_at is not None

        async with session_with_org(session_factory, str(ids.org_b)) as session:
            other_page = await list_operator_directives(
                session,
                DirectiveListArgs(
                    org_id=ids.org_b, state="all", agent_id=None, cursor=None, limit=50
                ),
            )
            with pytest.raises(ApiError) as err:
                await get_operator_directive(
                    session,
                    DirectiveDetailArgs(
                        org_id=ids.org_b, directive_id=ids.directive_a, usage_range="24h"
                    ),
                    now=NOW,
                )

        assert [row.id for row in other_page.data] == [ids.directive_b]
        assert err.value.code == NOT_FOUND
    finally:
        await _cleanup(session_factory, ids.org_a, ids.org_b)
