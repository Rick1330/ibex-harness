"""Positive controls for worker tenant paths under a non-superuser login.

A test that runs as the migration owner (``ibex``, superuser) bypasses RLS and
needs no role, so it cannot prove that ``SET LOCAL ROLE`` is doing anything.
Every test here connects as ``ibex_worker`` -- a ``NOINHERIT`` capability login
with no implicit tenant or purge privileges -- so a missing pin fails with
SQLSTATE 42501 instead of silently succeeding.

Red evidence for each test is recorded in the PR: removing the corresponding
``SET LOCAL ROLE`` makes it fail with ``permission denied``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import create_engine, create_session_factory, session_as_purge_org
from app.tasks import org_deletion
from app.tasks.billing_reconcile import SqlAlchemySpendStore

pytestmark = pytest.mark.integration


def _sql(statement: str):
    return text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        statement
    )


@pytest_asyncio.fixture
async def owner_factory(postgres_dsn: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Session factory for the migration owner login (seeding and assertions)."""
    engine = create_engine(Settings(database_url=postgres_dsn))
    try:
        yield create_session_factory(engine)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def worker_factory(
    capability_worker_dsn: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Session factory that logs in as ``ibex_worker`` (never the owner)."""
    engine = create_engine(Settings(database_url=capability_worker_dsn))
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            current_user = (await session.execute(_sql("SELECT current_user"))).scalar_one()
        assert current_user == "ibex_worker", current_user
        assert current_user != "ibex", "owner login would bypass RLS"
        yield factory
    finally:
        await engine.dispose()


async def _seed_org(
    factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    *,
    job_id: UUID | None = None,
) -> None:
    async with factory() as session, session.begin():
        await session.execute(
            _sql("INSERT INTO ibex_core.organizations (id, name, slug) VALUES (:id, :name, :slug)"),
            {"id": org_id, "name": f"Pin {org_id.hex[:8]}", "slug": f"pin-{org_id.hex[:12]}"},
        )
        if job_id is not None:
            await session.execute(
                _sql(
                    """
                    INSERT INTO ibex_core.org_deletion_jobs (id, org_id, status)
                    VALUES (:id, :org_id, 'pending')
                    """
                ),
                {"id": job_id, "org_id": org_id},
            )


async def _seed_period(
    factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    period_id: UUID,
    *,
    spent_cents: int = 0,
) -> None:
    async with factory() as session, session.begin():
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_billing.budget_periods
                    (id, org_id, period_start, period_end, cap_cents,
                     spent_cents_cached, enforcement_mode)
                VALUES (:id, :org_id, NOW() - interval '1 day', NOW() + interval '1 day',
                        100000, :spent, 'hard_cap')
                """
            ),
            {"id": period_id, "org_id": org_id, "spent": spent_cents},
        )


async def _seed_tenant_rows(
    factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    *,
    tag: str,
) -> tuple[UUID, UUID]:
    """Seed one agent + one user + one invite for ``org_id``; return user/agent ids."""
    user_id = uuid4()
    agent_id = uuid4()
    async with factory() as session, session.begin():
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_core.agents (id, org_id, name, slug)
                VALUES (:id, :org_id, :name, :slug)
                """
            ),
            {"id": agent_id, "org_id": org_id, "name": f"agent-{tag}", "slug": f"agent-{tag}"},
        )
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_core.users (id, org_id, email, name)
                VALUES (:id, :org_id, :email, :name)
                """
            ),
            {
                "id": user_id,
                "org_id": org_id,
                "email": f"user-{tag}@example.test",
                "name": f"user-{tag}",
            },
        )
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_core.organization_invites
                    (org_id, email, token_hash, expires_at)
                VALUES (:org_id, :email, :token_hash, NOW() + interval '1 day')
                """
            ),
            {
                "org_id": org_id,
                "email": f"invite-{tag}@example.test",
                "token_hash": f"hash-{tag}",
            },
        )
    return user_id, agent_id


async def _count(factory: async_sessionmaker[AsyncSession], statement: str, **params: object) -> int:
    async with factory() as session:
        return int((await session.execute(_sql(statement), params)).scalar_one())


async def _assert_worker_login(dsn: str) -> None:
    """Fail unless the DSN really authenticates as the capability login."""
    engine = create_engine(Settings(database_url=dsn))
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            current_user = (await session.execute(_sql("SELECT current_user"))).scalar_one()
    finally:
        await engine.dispose()
    assert current_user == "ibex_worker", current_user
    assert current_user != "ibex", "owner login would bypass RLS"


# ---------------------------------------------------------------------------
# Reconciliation: the definer read and the per-row tenant write.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_active_periods_reads_via_definer_as_worker_login(
    owner_factory: async_sessionmaker[AsyncSession],
    worker_factory: async_sessionmaker[AsyncSession],
    capability_worker_dsn: str,
) -> None:
    """Raw SELECT is 42501 for ibex_worker; the definer returns the period."""
    org_id = uuid4()
    period_id = uuid4()
    await _seed_org(owner_factory, org_id)
    await _seed_period(owner_factory, org_id, period_id)

    # The worker login cannot read the table directly (no grant, RLS forced).
    async with worker_factory() as session:
        with pytest.raises(ProgrammingError) as denied:
            await session.execute(_sql("SELECT 1 FROM ibex_billing.budget_periods LIMIT 1"))
    assert getattr(denied.value.orig, "sqlstate", None) == "42501", denied.value

    store = SqlAlchemySpendStore(capability_worker_dsn)
    try:
        periods = await store.list_active_periods()
    finally:
        await store.aclose()

    assert period_id in {UUID(period.period_id) for period in periods}
    assert org_id in {UUID(period.org_id) for period in periods}


@pytest.mark.asyncio
async def test_update_period_spent_pins_the_rows_org_as_worker_login(
    owner_factory: async_sessionmaker[AsyncSession],
    capability_worker_dsn: str,
) -> None:
    await _assert_worker_login(capability_worker_dsn)
    org_a, org_b = uuid4(), uuid4()
    period_a, period_b = uuid4(), uuid4()
    await _seed_org(owner_factory, org_a)
    await _seed_org(owner_factory, org_b)
    await _seed_period(owner_factory, org_a, period_a)
    await _seed_period(owner_factory, org_b, period_b)

    store = SqlAlchemySpendStore(capability_worker_dsn)
    try:
        await store.update_period_spent(str(period_a), str(org_a), 4200)
        # Wrong org for this period: the WHERE clause plus the org GUC must not
        # let a pinned transaction touch another tenant's row.
        await store.update_period_spent(str(period_b), str(org_a), 9999)
    finally:
        await store.aclose()

    assert (
        await _count(
            owner_factory,
            "SELECT spent_cents_cached FROM ibex_billing.budget_periods WHERE id = :id",
            id=period_a,
        )
        == 4200
    )
    assert (
        await _count(
            owner_factory,
            "SELECT spent_cents_cached FROM ibex_billing.budget_periods WHERE id = :id",
            id=period_b,
        )
        == 0
    )


# ---------------------------------------------------------------------------
# Erasure saga: the purge identity, end to end, from the worker login.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deletion_saga_erases_one_org_as_worker_login(
    owner_factory: async_sessionmaker[AsyncSession],
    capability_worker_dsn: str,
    require_redis: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _assert_worker_login(capability_worker_dsn)
    org_a, org_b = uuid4(), uuid4()
    job_id = uuid4()
    await _seed_org(owner_factory, org_a, job_id=job_id)
    await _seed_org(owner_factory, org_b)
    await _seed_tenant_rows(owner_factory, org_a, tag=org_a.hex[:8])
    await _seed_tenant_rows(owner_factory, org_b, tag=org_b.hex[:8])

    settings = Settings(
        database_url=capability_worker_dsn,
        redis_url=require_redis,
        org_deletion_deployed_stores="postgres",
    )
    monkeypatch.setattr(org_deletion, "get_settings", lambda: settings)

    out = await org_deletion._run_delete(job_id=str(job_id), org_id=str(org_a))
    assert out["status"] == "succeeded", out

    org_row = (
        await _one(
            owner_factory,
            "SELECT status, deleted_at FROM ibex_core.organizations WHERE id = :id",
            id=org_a,
        )
    )
    assert org_row[0] == "cancelled"
    assert org_row[1] is not None

    for table in ("agents", "users", "organization_invites"):
        assert (
            await _count(
                owner_factory,
                f"SELECT count(*) FROM ibex_core.{table} WHERE org_id = :org",
                org=org_a,
            )
            == 0
        ), table
        assert (
            await _count(
                owner_factory,
                f"SELECT count(*) FROM ibex_core.{table} WHERE org_id = :org",
                org=org_b,
            )
            == 1
        ), table

    job_status = (
        await _one(
            owner_factory,
            "SELECT status FROM ibex_core.org_deletion_jobs WHERE id = :id",
            id=job_id,
        )
    )[0]
    assert job_status == "succeeded"

    receipts = {
        row[0]: row[1]
        for row in (
            await _all(
                owner_factory,
                "SELECT store, status FROM ibex_core.deletion_store_receipts WHERE job_id = :id",
                id=job_id,
            )
        )
    }
    assert receipts["postgres"] == "verified"
    assert receipts["clickhouse"] == "not_applicable"


# ---------------------------------------------------------------------------
# Purge cannot overreach: the pin is real reach, scoped to one org.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_pin_reaches_the_org_but_not_another_org(
    owner_factory: async_sessionmaker[AsyncSession],
    worker_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_a, org_b = uuid4(), uuid4()
    await _seed_org(owner_factory, org_a)
    await _seed_org(owner_factory, org_b)
    user_a, _ = await _seed_tenant_rows(owner_factory, org_a, tag=org_a.hex[:8])
    user_b, _ = await _seed_tenant_rows(owner_factory, org_b, tag=org_b.hex[:8])

    async with session_as_purge_org(worker_factory, str(org_a)) as session:
        overreach = await session.execute(
            _sql("DELETE FROM ibex_core.users WHERE org_id = CAST(:org AS uuid)"),
            {"org": str(org_b)},
        )
        assert overreach.rowcount == 0, "purge deleted another tenant's row"
        own = await session.execute(
            _sql("DELETE FROM ibex_core.users WHERE org_id = CAST(:org AS uuid)"),
            {"org": str(org_a)},
        )
        assert own.rowcount == 1, "the pinned role must reach its own org"

    assert (
        await _count(
            owner_factory, "SELECT count(*) FROM ibex_core.users WHERE id = :id", id=user_a
        )
        == 0
    )
    assert (
        await _count(
            owner_factory, "SELECT count(*) FROM ibex_core.users WHERE id = :id", id=user_b
        )
        == 1
    )


async def _one(factory: async_sessionmaker[AsyncSession], statement: str, **params: object):
    async with factory() as session:
        return (await session.execute(_sql(statement), params)).one()


async def _all(factory: async_sessionmaker[AsyncSession], statement: str, **params: object):
    async with factory() as session:
        return (await session.execute(_sql(statement), params)).all()


# ---------------------------------------------------------------------------
# SET LOCAL, never SET ROLE: a pooled connection must not carry the identity.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pinned_role_does_not_leak_on_a_pooled_connection(
    capability_worker_dsn: str,
) -> None:
    """With one pooled connection, the next transaction is the login again."""
    from ibex_async_db import parse_async_database_url
    from sqlalchemy.ext.asyncio import create_async_engine

    target = parse_async_database_url(capability_worker_dsn)
    engine = create_async_engine(
        target.url,
        pool_size=1,
        max_overflow=0,
        connect_args=dict(target.connect_args),
    )
    factory = create_session_factory(engine)
    try:
        async with session_as_purge_org(factory, str(uuid4())) as session:
            assert (
                await session.execute(_sql("SELECT current_user"))
            ).scalar_one() == "ibex_purge"
        # Same pooled connection; SET LOCAL must have been rolled back.
        async with factory() as session:
            assert (
                await session.execute(_sql("SELECT current_user"))
            ).scalar_one() == "ibex_worker"
    finally:
        await engine.dispose()

