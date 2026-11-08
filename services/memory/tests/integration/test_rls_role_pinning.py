"""RLS is real only when the transaction pins a non-superuser role (P0-06).

``FORCE ROW LEVEL SECURITY`` makes a table owner subject to the table's own
policies; a superuser, or any role with ``BYPASSRLS``, still bypasses RLS before
the policy is consulted. The reference DSN connects as the bootstrap superuser,
so these tests pin ``ibex_app`` through the production helper and assert that
even an unfiltered ``SELECT`` returns one tenant's rows only.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db import session_with_org
from app.exceptions import MemoryNotFoundError
from app.lifecycle import ForgetMemory, forget_memory_session
from app.org_context import set_service_org
from app.vectorstore.base import SearchRequest, UpsertRequest
from app.vectorstore.pgvector_store import PgVectorStore
from tests.integration.conftest import zero_embedding

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
        "agent_a": agent_a,
        "agent_b": agent_b,
        "memory_a": memory_a,
        "memory_b": memory_b,
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


@pytest.fixture
def statement_log(engine: AsyncEngine):
    """Record every SQL statement the engine sends, in order."""
    recorded: list[str] = []

    def _record(conn, cursor, statement, params, context, executemany) -> None:
        del conn, cursor, params, context, executemany
        recorded.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _record)
    try:
        yield recorded
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _record)


def _pins_role(statements: list[str]) -> bool:
    return any("SET LOCAL ROLE ibex_app" in line for line in statements)


def _sets_bypass(statements: list[str]) -> bool:
    return any("set_config('app.is_service_account', 'true'" in line for line in statements)


@pytest.mark.asyncio
async def test_vector_store_operations_pin_the_tenant_role(
    store: PgVectorStore,
    session_factory: async_sessionmaker[AsyncSession],
    statement_log: list[str],
) -> None:
    """PgVectorStore upsert/search/delete must pin ibex_app and never set the bypass."""
    seed = await _seed_two_tenants(session_factory)
    org_a, org_b = UUID(seed["org_a"]), UUID(seed["org_b"])
    agent_a = UUID(seed["agent_a"])
    memory_a, memory_b = UUID(seed["memory_a"]), UUID(seed["memory_b"])
    vector = zero_embedding(hotspot=3)
    for org, memory in ((org_a, memory_a), (org_b, memory_b)):
        await store.upsert(
            UpsertRequest(
                memory_id=memory,
                org_id=org,
                embedding=vector,
                embedding_model="test",
                expected_revision=1,
            )
        )

    statement_log.clear()
    hits = await store.search(
        SearchRequest(
            org_id=org_a,
            agent_id=agent_a,
            query_embedding=vector,
            limit=10,
            min_similarity=0.0,
        )
    )
    assert _pins_role(statement_log), "search must pin the tenant role"
    assert not _sets_bypass(statement_log), "search must not set the service bypass"
    assert [hit.memory_id for hit in hits] == [memory_a], "search leaked another tenant"

    statement_log.clear()
    await store.upsert(
        UpsertRequest(
            memory_id=memory_a,
            org_id=org_a,
            embedding=vector,
            embedding_model="test",
            expected_revision=1,
        )
    )
    assert _pins_role(statement_log), "upsert must pin the tenant role"
    assert not _sets_bypass(statement_log), "upsert must not set the service bypass"

    statement_log.clear()
    await store.delete(memory_id=memory_a, org_id=org_a, expected_revision=1)
    assert _pins_role(statement_log), "delete must pin the tenant role"
    assert not _sets_bypass(statement_log), "delete must not set the service bypass"

    # The tenant-owned row survived the other tenant's operations.
    async with session_with_org(session_factory, seed["org_b"]) as session:
        remaining = (
            await session.execute(text("SELECT count(*) FROM ibex_core.memories"))
        ).scalar_one()
    assert remaining == 1


@pytest.mark.asyncio
async def test_pinned_transaction_discards_an_inherited_bypass(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A session that already set the bypass must not keep it past the pin."""
    seed = await _seed_two_tenants(session_factory)
    org_a, org_b = seed["org_a"], seed["org_b"]

    async with session_factory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.is_service_account', 'true', true)")
        )
        await set_service_org(session, UUID(org_a))
        visible = (
            await session.execute(text("SELECT count(*) FROM ibex_core.memories"))
        ).scalar_one()
        other = (
            await session.execute(
                text("SELECT count(*) FROM ibex_core.memories WHERE org_id = :org"),
                {"org": org_b},
            )
        ).scalar_one()

    assert visible == 1, "the inherited bypass must be cleared by the pin"
    assert other == 0


async def _forget_as_tenant(factory, *, org_id, agent_id, memory_id) -> None:
    async with session_with_org(factory, org_id) as session:
        await forget_memory_session(
            session,
            ForgetMemory(
                org_id=org_id,
                agent_id=agent_id,
                memory_id=memory_id,
                expected_revision=1,
            ),
        )


@pytest.mark.asyncio
async def test_forget_cannot_touch_another_tenant(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_two_tenants(session_factory)
    org_a, memory_a = seed["org_a"], seed["memory_a"]

    refusal = _forget_as_tenant(
        session_factory,
        org_id=seed["org_b"],
        agent_id=seed["agent_b"],
        memory_id=seed["memory_a"],
    )
    with pytest.raises(MemoryNotFoundError):
        await refusal

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
