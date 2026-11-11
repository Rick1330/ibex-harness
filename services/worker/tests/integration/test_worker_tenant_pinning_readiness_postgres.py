"""Readiness controls: sessions, dead letters, and /ready under a tenant pin.

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

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.enqueue_http as enqueue_http_module
import app.repositories.failed_tasks as failed_tasks_module
from app.config import Settings
from app.db import session_as_app, session_unpinned
from app.enqueue_http import create_enqueue_app
from app.extraction import session_store as session_store_module
from app.extraction.session_store import PostgresSessionStore
from app.idempotency_ledger import LedgerError, PostgresIdempotencyLedger
from app.repositories.failed_tasks import insert_failed_task
from tests.integration.tenant_pinning_support import (
    SessionSeed,
    assert_worker_login,
    count_rows,
    failed_record,
    fetch_one,
    pinned_ledger,
    seed_org,
    seed_session,
    seed_tenant_rows,
    sql_text,
    sqlstate,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Extraction pointer: SELECT/UPDATE ibex_core.sessions as the worker login.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_store_pins_the_org_as_worker_login(
    owner_factory: async_sessionmaker[AsyncSession],
    worker_factory: async_sessionmaker[AsyncSession],
    capability_worker_dsn: str,
) -> None:
    await assert_worker_login(capability_worker_dsn)
    org_id, session_id = uuid4(), uuid4()
    await seed_org(owner_factory, org_id)
    _, agent_id = await seed_tenant_rows(owner_factory, org_id, tag=org_id.hex[:8])
    await seed_session(
        owner_factory,
        SessionSeed(org_id=org_id, agent_id=agent_id, session_id=session_id),
    )

    store = PostgresSessionStore(worker_factory)
    snapshot = await store._load(org_id, session_id)
    assert snapshot is not None and snapshot.last_extracted_turn == 5
    await store._update(org_id, session_id, 9, expected_lifecycle_revision=1)
    assert (
        await count_rows(
            owner_factory,
            "SELECT last_extracted_turn FROM ibex_core.sessions WHERE id = :id",
            id=session_id,
        )
        == 9
    )


@pytest.mark.asyncio
async def test_session_store_without_the_pin_is_42501(
    owner_factory: async_sessionmaker[AsyncSession],
    worker_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id, session_id = uuid4(), uuid4()
    await seed_org(owner_factory, org_id)
    _, agent_id = await seed_tenant_rows(owner_factory, org_id, tag=org_id.hex[:8])
    await seed_session(
        owner_factory,
        SessionSeed(org_id=org_id, agent_id=agent_id, session_id=session_id),
    )
    monkeypatch.setattr(
        session_store_module,
        "session_as_app_org",
        lambda factory, _org: session_unpinned(factory),
    )
    with pytest.raises(ProgrammingError) as err:
        await PostgresSessionStore(worker_factory)._load(org_id, session_id)
    assert sqlstate(err.value) == "42501", err.value


# ---------------------------------------------------------------------------
# Dead-letter store: no RLS, nullable org_id, INSERT-only grant, no org GUC.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_tasks_insert_uses_pinned_app_without_an_org_guc(
    owner_factory: async_sessionmaker[AsyncSession],
    worker_factory: async_sessionmaker[AsyncSession],
    capability_worker_dsn: str,
) -> None:
    await assert_worker_login(capability_worker_dsn)
    task_id = f"pinned-{uuid4()}"
    assert await insert_failed_task(worker_factory, failed_record(task_id)) is True
    row = await fetch_one(
        owner_factory,
        "SELECT org_id, task_name FROM ibex_core.failed_tasks WHERE task_id = :id",
        id=task_id,
    )
    assert row[0] is None
    assert row[1] == "ibex.worker.maintenance.always_fail"
    # A duplicate task_id is a skipped insert, not a second row and not an
    # error; the untargeted ON CONFLICT keeps that working with INSERT only.
    assert await insert_failed_task(worker_factory, failed_record(task_id)) is False
    assert (
        await count_rows(
            owner_factory,
            "SELECT count(*) FROM ibex_core.failed_tasks WHERE task_id = :id",
            id=task_id,
        )
        == 1
    )

    # The scope the insert uses binds no tenant: a GUC here would imply an
    # isolation the table does not have.
    async with session_as_app(worker_factory) as session:
        unset = (
            await session.execute(sql_text("SELECT current_setting('app.current_org_id', true)"))
        ).scalar_one()
    assert unset is None


@pytest.mark.asyncio
async def test_failed_tasks_insert_without_the_pin_is_42501(
    worker_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        failed_tasks_module, "session_as_app", lambda factory: session_unpinned(factory)
    )
    with pytest.raises(ProgrammingError) as err:
        await insert_failed_task(worker_factory, failed_record(f"unpinned-{uuid4()}"))
    assert sqlstate(err.value) == "42501", err.value


# ---------------------------------------------------------------------------
# Enqueue idempotency ledger: injected scopes, ping, and /ready on the login.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idempotency_ledger_ping_and_claim_with_injected_scopes(
    owner_factory: async_sessionmaker[AsyncSession],
    worker_factory: async_sessionmaker[AsyncSession],
    capability_worker_dsn: str,
) -> None:
    await assert_worker_login(capability_worker_dsn)
    org_id, agent_id = uuid4(), uuid4()
    await seed_org(owner_factory, org_id)
    async with owner_factory() as session, session.begin():
        await session.execute(
            sql_text(
                """
                INSERT INTO ibex_core.agents (id, org_id, name, slug)
                VALUES (:id, :org, :name, :slug)
                """
            ),
            {
                "id": agent_id,
                "org": org_id,
                "name": f"ledger-{agent_id.hex[:8]}",
                "slug": f"ledger-{agent_id.hex[:12]}",
            },
        )

    ledger = pinned_ledger(worker_factory)
    await ledger.ping()
    claim = await ledger.claim(
        org_id=org_id, agent_id=agent_id, key="pinned-key", request_hash="f" * 64
    )
    assert claim.kind == "owned" and claim.claim is not None
    await ledger.finalize(claim.claim, status=202, response=b'{"task_id":"pinned"}')


@pytest.mark.asyncio
async def test_idempotency_ledger_default_scope_is_not_ready_on_worker_login(
    worker_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The package default only writes the retired GUC; the pin is load-bearing."""
    default_ledger = PostgresIdempotencyLedger(worker_factory)
    with pytest.raises(LedgerError, match="idempotency ledger is not ready"):
        await default_ledger.ping()


@pytest.mark.asyncio
async def test_enqueue_ready_is_ready_on_the_worker_login(
    capability_worker_dsn: str,
    require_redis: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ping that quietly reports not-ready is the failure this guards."""
    await assert_worker_login(capability_worker_dsn)

    async def _ready_broker(_url: str):
        from starlette.responses import JSONResponse

        return JSONResponse({"status": "ready", "service": "worker"})

    monkeypatch.setattr("app.enqueue_http._ping_broker", _ready_broker)
    settings = Settings(
        database_url=capability_worker_dsn,
        redis_url=require_redis,
        enqueue_api_token=SecretStr("ready-token"),
    )
    created: dict[str, object] = {}
    real_create_engine = enqueue_http_module.create_engine

    def _capture_engine(settings_: Settings):
        engine = real_create_engine(settings_)
        created["engine"] = engine
        return engine

    monkeypatch.setattr(enqueue_http_module, "create_engine", _capture_engine)
    # No ledger argument: the production construction site must inject the
    # pinned scopes itself.
    app = create_enqueue_app(settings)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/ready")
    finally:
        await created["engine"].dispose()  # type: ignore[union-attr]
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ready"
