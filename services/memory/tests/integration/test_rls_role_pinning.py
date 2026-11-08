"""RLS is real only when the transaction pins a non-superuser role (P0-06).

The reference DSN connects as a role that owns the tables, and a table owner or
superuser bypasses row-level security regardless of ``FORCE``. These tests pin
``ibex_app`` through the production helper and assert that even an unfiltered
``SELECT`` returns one tenant's rows only.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import session_with_org
from app.exceptions import MemoryNotFoundError
from app.org_context import set_service_org
from app.lifecycle import ForgetMemory, forget_memory_session

pytestmark = pytest.mark.integration


async def _seed_two_tenants(
    factory: async_sessionmaker[AsyncSession],
) -> dict[str, str]:
    """Seed one agent and one memory in each of two organizations."""
    org_a, org_b = str(uuid4()), str(uuid4())
    agent_a, agent_b = str(uuid4()), str(uuid4())
    memory_a, memory_b = str(uuid4()), str(uuid4())
    async with factory() as session, session.begin():
        for org, agent, memory, label in (
            (org_a, agent_a, memory_a, "tenant-a sentinel"),
            (org_b, agent_b, memory_b, "tenant-b sentinel"),
        ):
            await session.execute(
                text(
                    "INSERT INTO ibex_core.organizations (id, name, slug, status)"
                    " VALUES (:id, :name, :slug, 'active')"
                ),
                {"id": org, "name": f"rls {label}", "slug": f"rls-{org}"},
            )
            await session.execute(
                text(
                    "INSERT INTO ibex_core.agents (id, org_id, name, slug, status)"
                    " VALUES (:id, :org, 'rls agent', :slug, 'active')"
                ),
                {"id": agent, "org": org, "slug": f"agent-{agent}"},
            )
            await session.execute(
                text(
                    "INSERT INTO ibex_core.memories"
                    " (id, org_id, agent_id, content, content_hash, content_tokens)"
                    " VALUES (:id, :org, :agent, :content, :hash, 3)"
                ),
                {
                    "id": memory,
                    "org": org,
                    "agent": agent,
                    "content": label,
                    "hash": f"hash-{memory}",
                },
            )
    return {
        "org_a": org_a,
        "org_b": org_b,
        "agent_b": agent_b,
        "memory_a": memory_a,
    }


@pytest.mark.asyncio
async def test_unfiltered_select_returns_only_the_pinned_org(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_two_tenants(session_factory)
    org_a, org_b = seed["org_a"], seed["org_b"]

    async with session_with_org(session_factory, org_a) as session:
        visible = (
            await session.execute(text("SELECT count(*) FROM ibex_core.memories"))
        ).scalar_one()
        other = (
            await session.execute(
                text("SELECT count(*) FROM ibex_core.memories WHERE org_id = :org"),
                {"org": org_b},
            )
        ).scalar_one()

    assert visible == 1, "the pinned tenant must see exactly its own row"
    assert other == 0, "RLS must hide the other tenant behind an explicit filter"


@pytest.mark.asyncio
async def test_set_service_org_pins_the_role_for_the_vector_path(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The production helper, used by PgVectorStore, must pin ibex_app."""
    seed = await _seed_two_tenants(session_factory)
    org_a, org_b = seed["org_a"], seed["org_b"]

    async with session_factory() as session, session.begin():
        await set_service_org(session, org_a)
        visible = (
            await session.execute(text("SELECT count(*) FROM ibex_core.memories"))
        ).scalar_one()
        other = (
            await session.execute(
                text("SELECT count(*) FROM ibex_core.memories WHERE org_id = :org"),
                {"org": org_b},
            )
        ).scalar_one()

    assert visible == 1
    assert other == 0


@pytest.mark.asyncio
async def test_forget_cannot_touch_another_tenant(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_two_tenants(session_factory)
    org_a, memory_a = seed["org_a"], seed["memory_a"]

    with pytest.raises(MemoryNotFoundError):
        async with session_with_org(session_factory, seed["org_b"]) as session:
            await forget_memory_session(
                session,
                ForgetMemory(
                    org_id=seed["org_b"],
                    agent_id=seed["agent_b"],
                    memory_id=seed["memory_a"],
                    expected_revision=1,
                ),
            )

    async with session_with_org(session_factory, seed["org_b"]) as session:
        visible_to_b = (
            await session.execute(text("SELECT count(*) FROM ibex_core.memories"))
        ).scalar_one()

    async with session_with_org(session_factory, org_a) as session:
        row = (
            await session.execute(
                text(
                    "SELECT content, tombstoned FROM ibex_core.memories WHERE id = :id"
                ),
                {"id": memory_a},
            )
        ).one()

    assert visible_to_b == 1, "tenant B must not see tenant A's row after the refusal"
    assert row.content == "tenant-a sentinel"
    assert row.tombstoned is False
