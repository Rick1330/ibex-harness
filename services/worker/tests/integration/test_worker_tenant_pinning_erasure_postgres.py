"""Erasure-saga controls: the purge pin reaches one org and never leaks.

A test that runs as the migration owner (``ibex``, superuser) bypasses RLS and
needs no role, so it cannot prove that ``SET LOCAL ROLE`` is doing anything.
Every test here connects as ``ibex_worker`` -- a ``NOINHERIT`` capability login
with no implicit tenant or purge privileges -- so a missing pin fails with
SQLSTATE 42501 instead of silently succeeding.

Red evidence for each test is recorded in the PR: removing the corresponding
``SET LOCAL ROLE`` makes it fail with ``permission denied``.

The shared premise and helpers live in ``tenant_pinning_support``.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import create_session_factory, session_as_app_org, session_as_purge_org
from app.tasks import org_deletion
from tests.integration.tenant_pinning_support import (
    assert_worker_login,
    count_rows,
    fetch_all,
    fetch_one,
    seed_org,
    seed_tenant_rows,
    sql_text,
)

pytestmark = pytest.mark.integration


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
    await assert_worker_login(capability_worker_dsn)
    org_a, org_b = uuid4(), uuid4()
    job_id = uuid4()
    await seed_org(owner_factory, org_a, job_id=job_id)
    await seed_org(owner_factory, org_b)
    await seed_tenant_rows(owner_factory, org_a, tag=org_a.hex[:8])
    await seed_tenant_rows(owner_factory, org_b, tag=org_b.hex[:8])

    settings = Settings(
        database_url=capability_worker_dsn,
        redis_url=require_redis,
        org_deletion_deployed_stores="postgres",
    )
    monkeypatch.setattr(org_deletion, "get_settings", lambda: settings)

    out = await org_deletion._run_delete(job_id=str(job_id), org_id=str(org_a))
    assert out["status"] == "succeeded", out

    org_row = (
        await fetch_one(
            owner_factory,
            "SELECT status, deleted_at FROM ibex_core.organizations WHERE id = :id",
            id=org_a,
        )
    )
    assert org_row[0] == "cancelled"
    assert org_row[1] is not None

    for table in ("agents", "users", "organization_invites"):
        assert (
            await count_rows(
                owner_factory,
                f"SELECT count(*) FROM ibex_core.{table} WHERE org_id = :org",
                org=org_a,
            )
            == 0
        ), table
        assert (
            await count_rows(
                owner_factory,
                f"SELECT count(*) FROM ibex_core.{table} WHERE org_id = :org",
                org=org_b,
            )
            == 1
        ), table

    job_status = (
        await fetch_one(
            owner_factory,
            "SELECT status FROM ibex_core.org_deletion_jobs WHERE id = :id",
            id=job_id,
        )
    )[0]
    assert job_status == "succeeded"

    receipts = {
        row[0]: row[1]
        for row in (
            await fetch_all(
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
    await seed_org(owner_factory, org_a)
    await seed_org(owner_factory, org_b)
    user_a, _ = await seed_tenant_rows(owner_factory, org_a, tag=org_a.hex[:8])
    user_b, _ = await seed_tenant_rows(owner_factory, org_b, tag=org_b.hex[:8])

    async with session_as_purge_org(worker_factory, str(org_a)) as session:
        overreach = await session.execute(
            sql_text("DELETE FROM ibex_core.users WHERE org_id = CAST(:org AS uuid)"),
            {"org": str(org_b)},
        )
        assert overreach.rowcount == 0, "purge deleted another tenant's row"
        own = await session.execute(
            sql_text("DELETE FROM ibex_core.users WHERE org_id = CAST(:org AS uuid)"),
            {"org": str(org_a)},
        )
        assert own.rowcount == 1, "the pinned role must reach its own org"

    assert (
        await count_rows(
            owner_factory, "SELECT count(*) FROM ibex_core.users WHERE id = :id", id=user_a
        )
        == 0
    )
    assert (
        await count_rows(
            owner_factory, "SELECT count(*) FROM ibex_core.users WHERE id = :id", id=user_b
        )
        == 1
    )


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
                await session.execute(sql_text("SELECT current_user"))
            ).scalar_one() == "ibex_purge"
        # Same pooled connection; SET LOCAL must have been rolled back.
        async with factory() as session:
            assert (
                await session.execute(sql_text("SELECT current_user"))
            ).scalar_one() == "ibex_worker"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# SET LOCAL, never SET ROLE: the app identity must not outlive its transaction.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_app_scope_does_not_leak_on_a_pooled_connection(
    capability_worker_dsn: str,
) -> None:
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
        async with session_as_app_org(factory, str(uuid4())) as session:
            assert (
                await session.execute(sql_text("SELECT current_user"))
            ).scalar_one() == "ibex_app"
        # Same pooled connection; SET LOCAL must have been rolled back.
        async with factory() as session:
            assert (
                await session.execute(sql_text("SELECT current_user"))
            ).scalar_one() == "ibex_worker"
    finally:
        await engine.dispose()
