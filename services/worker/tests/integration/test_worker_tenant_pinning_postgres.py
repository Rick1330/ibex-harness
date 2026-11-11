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

import json
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.budget_ledger as budget_ledger_module
import app.enqueue_http as enqueue_http_module
import app.repositories.failed_tasks as failed_tasks_module
from app.budget_ledger import (
    COMPLETENESS_COMPLETE,
    BudgetClaimRequest,
    BudgetLedgerError,
    BudgetLedgerUnavailableError,
    _AsyncBudgetLedger,
)
from app.config import Settings
from app.db import (
    app_org_scope,
    app_probe_scope,
    create_engine,
    create_session_factory,
    session_as_app,
    session_as_app_org,
    session_as_purge_org,
    session_unpinned,
)
from app.enqueue_http import create_enqueue_app
from app.extraction import session_store as session_store_module
from app.extraction.session_store import PostgresSessionStore
from app.idempotency_ledger import LedgerError, PostgresIdempotencyLedger
from app.repositories.failed_tasks import FailedTaskRecord, insert_failed_task
from app.tasks import capture_redaction, org_deletion
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



# ---------------------------------------------------------------------------
# Budget ledger: capability probe + claim/finalize/release as the worker login.
# ---------------------------------------------------------------------------


def _sqlstate(exc: BaseException | None) -> str | None:
    return getattr(getattr(exc, "orig", None), "sqlstate", None)


async def _seed_rate_card(
    factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    card_id: UUID,
) -> None:
    prices = json.dumps(
        [
            {
                "provider": "openai",
                "model_pattern": "gpt-4o*",
                "input_cents_per_1k": 10,
                "output_cents_per_1k": 30,
            }
        ]
    )
    async with factory() as session, session.begin():
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_billing.rate_cards (id, org_id, name, status)
                VALUES (:id, :org, :name, 'published')
                """
            ),
            {"id": card_id, "org": org_id, "name": f"card-{card_id.hex[:8]}"},
        )
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_billing.rate_card_versions
                    (rate_card_id, org_id, version, prices)
                VALUES (:id, :org, 1, CAST(:prices AS jsonb))
                """
            ),
            {"id": card_id, "org": org_id, "prices": prices},
        )


def _budget_request(org_id: UUID, agent_id: UUID, *, key: str) -> BudgetClaimRequest:
    return BudgetClaimRequest(
        org_id=org_id,
        agent_id=agent_id,
        key=key,
        request_hash="a" * 64,
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=100,
        output_tokens=200,
    )


@pytest.mark.asyncio
async def test_budget_ping_reports_ready_as_worker_login(
    worker_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Unpinned the probe reads current_user=ibex_worker and reports not ready."""
    await _AsyncBudgetLedger(worker_factory).ping()


@pytest.mark.asyncio
async def test_budget_ping_without_the_pin_reports_not_ready(
    worker_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        budget_ledger_module, "session_as_app", lambda factory: session_unpinned(factory)
    )
    with pytest.raises(BudgetLedgerError, match="budget reservation ledger is not ready"):
        await _AsyncBudgetLedger(worker_factory).ping()


@pytest.mark.asyncio
async def test_budget_claim_finalize_release_pin_the_org_as_worker_login(
    owner_factory: async_sessionmaker[AsyncSession],
    worker_factory: async_sessionmaker[AsyncSession],
    capability_worker_dsn: str,
) -> None:
    await _assert_worker_login(capability_worker_dsn)
    org_id = uuid4()
    period_id = uuid4()
    card_id = uuid4()
    await _seed_org(owner_factory, org_id)
    _, agent_id = await _seed_tenant_rows(owner_factory, org_id, tag=org_id.hex[:8])
    await _seed_period(owner_factory, org_id, period_id)
    await _seed_rate_card(owner_factory, org_id, card_id)

    ledger = _AsyncBudgetLedger(worker_factory)
    claim = await ledger.claim(_budget_request(org_id, agent_id, key="pinned-claim"))
    assert claim is not None
    assert claim.org_id == org_id
    assert (
        await ledger.finalize(claim, input_tokens=100, output_tokens=200)
        == COMPLETENESS_COMPLETE
    )

    released = await ledger.claim(_budget_request(org_id, agent_id, key="pinned-release"))
    assert released is not None
    await ledger.release(released)

    state = (
        await _one(
            owner_factory,
            "SELECT state FROM ibex_core.budget_reservations WHERE id = :id",
            id=released.claim_id,
        )
    )[0]
    assert state == "released"


@pytest.mark.asyncio
async def test_budget_claim_without_the_pin_is_42501(
    owner_factory: async_sessionmaker[AsyncSession],
    worker_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = uuid4()
    await _seed_org(owner_factory, org_id)
    _, agent_id = await _seed_tenant_rows(owner_factory, org_id, tag=org_id.hex[:8])
    monkeypatch.setattr(
        budget_ledger_module,
        "session_as_app_org",
        lambda factory, _org: session_unpinned(factory),
    )
    with pytest.raises(BudgetLedgerUnavailableError) as err:
        await _AsyncBudgetLedger(worker_factory).claim(
            _budget_request(org_id, agent_id, key="unpinned-claim")
        )
    assert _sqlstate(err.value.__cause__) == "42501", err.value


# ---------------------------------------------------------------------------
# Capture redaction: the policy read and the memory update as the worker login.
# ---------------------------------------------------------------------------


async def _seed_capture_policy(
    factory: async_sessionmaker[AsyncSession], org_id: UUID
) -> None:
    async with factory() as session, session.begin():
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_core.org_capture_policies (org_id, agent_id, mode, priority)
                VALUES (:org, NULL, 'metadata_only', 0)
                """
            ),
            {"org": org_id},
        )


@pytest.mark.asyncio
async def test_capture_redaction_reads_the_policy_as_worker_login(
    owner_factory: async_sessionmaker[AsyncSession],
    capability_worker_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _assert_worker_login(capability_worker_dsn)
    org_id = uuid4()
    await _seed_org(owner_factory, org_id)
    await _seed_capture_policy(owner_factory, org_id)
    monkeypatch.setattr(
        capture_redaction,
        "get_settings",
        lambda: Settings(database_url=capability_worker_dsn),
    )
    out = await capture_redaction._run(capture_redaction._CaptureJob(org_id=str(org_id)))
    assert out == {"status": "redacted", "mode": "metadata_only"}


@pytest.mark.asyncio
async def test_capture_redaction_without_the_pin_is_42501(
    owner_factory: async_sessionmaker[AsyncSession],
    capability_worker_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = uuid4()
    await _seed_org(owner_factory, org_id)
    await _seed_capture_policy(owner_factory, org_id)
    monkeypatch.setattr(
        capture_redaction,
        "get_settings",
        lambda: Settings(database_url=capability_worker_dsn),
    )
    monkeypatch.setattr(
        capture_redaction,
        "session_as_app_org",
        lambda factory, _org: session_unpinned(factory),
    )
    with pytest.raises(ProgrammingError) as err:
        await capture_redaction._run(capture_redaction._CaptureJob(org_id=str(org_id)))
    assert _sqlstate(err.value) == "42501", err.value


# ---------------------------------------------------------------------------
# Extraction pointer: SELECT/UPDATE ibex_core.sessions as the worker login.
# ---------------------------------------------------------------------------


async def _seed_session(
    factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    agent_id: UUID,
    session_id: UUID,
    *,
    turn: int = 5,
) -> None:
    async with factory() as session, session.begin():
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_core.sessions (
                    id, org_id, agent_id, status, model, provider, last_extracted_turn
                ) VALUES (
                    :id, :org, :agent, 'completed', 'gpt-4o-mini', 'openai', :turn
                )
                """
            ),
            {"id": session_id, "org": org_id, "agent": agent_id, "turn": turn},
        )


@pytest.mark.asyncio
async def test_session_store_pins_the_org_as_worker_login(
    owner_factory: async_sessionmaker[AsyncSession],
    worker_factory: async_sessionmaker[AsyncSession],
    capability_worker_dsn: str,
) -> None:
    await _assert_worker_login(capability_worker_dsn)
    org_id, session_id = uuid4(), uuid4()
    await _seed_org(owner_factory, org_id)
    _, agent_id = await _seed_tenant_rows(owner_factory, org_id, tag=org_id.hex[:8])
    await _seed_session(owner_factory, org_id, agent_id, session_id)

    store = PostgresSessionStore(worker_factory)
    snapshot = await store._load(org_id, session_id)
    assert snapshot is not None and snapshot.last_extracted_turn == 5
    await store._update(org_id, session_id, 9, expected_lifecycle_revision=1)
    assert (
        await _count(
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
    await _seed_org(owner_factory, org_id)
    _, agent_id = await _seed_tenant_rows(owner_factory, org_id, tag=org_id.hex[:8])
    await _seed_session(owner_factory, org_id, agent_id, session_id)
    monkeypatch.setattr(
        session_store_module,
        "session_as_app_org",
        lambda factory, _org: session_unpinned(factory),
    )
    with pytest.raises(ProgrammingError) as err:
        await PostgresSessionStore(worker_factory)._load(org_id, session_id)
    assert _sqlstate(err.value) == "42501", err.value


# ---------------------------------------------------------------------------
# Dead-letter store: no RLS, nullable org_id, INSERT-only grant, no org GUC.
# ---------------------------------------------------------------------------


def _failed_record(task_id: str) -> FailedTaskRecord:
    return FailedTaskRecord(
        task_name="ibex.worker.maintenance.always_fail",
        task_id=task_id,
        args=[],
        kwargs={},
        exception_type="RuntimeError",
        exception_message="pinned dead letter",
        traceback_text="traceback",
        retry_count=3,
        org_id=None,
    )


@pytest.mark.asyncio
async def test_failed_tasks_insert_uses_pinned_app_without_an_org_guc(
    owner_factory: async_sessionmaker[AsyncSession],
    worker_factory: async_sessionmaker[AsyncSession],
    capability_worker_dsn: str,
) -> None:
    await _assert_worker_login(capability_worker_dsn)
    task_id = f"pinned-{uuid4()}"
    assert await insert_failed_task(worker_factory, _failed_record(task_id)) is True
    row = await _one(
        owner_factory,
        "SELECT org_id, task_name FROM ibex_core.failed_tasks WHERE task_id = :id",
        id=task_id,
    )
    assert row[0] is None
    assert row[1] == "ibex.worker.maintenance.always_fail"
    # A duplicate task_id is a skipped insert, not a second row and not an
    # error; the untargeted ON CONFLICT keeps that working with INSERT only.
    assert await insert_failed_task(worker_factory, _failed_record(task_id)) is False
    assert (
        await _count(
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
            await session.execute(_sql("SELECT current_setting('app.current_org_id', true)"))
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
        await insert_failed_task(worker_factory, _failed_record(f"unpinned-{uuid4()}"))
    assert _sqlstate(err.value) == "42501", err.value


# ---------------------------------------------------------------------------
# Enqueue idempotency ledger: injected scopes, ping, and /ready on the login.
# ---------------------------------------------------------------------------


def _pinned_ledger(factory: async_sessionmaker[AsyncSession]) -> PostgresIdempotencyLedger:
    return PostgresIdempotencyLedger(
        factory,
        session_scope=app_org_scope(factory),
        probe_scope=app_probe_scope(factory),
    )


@pytest.mark.asyncio
async def test_idempotency_ledger_ping_and_claim_with_injected_scopes(
    owner_factory: async_sessionmaker[AsyncSession],
    worker_factory: async_sessionmaker[AsyncSession],
    capability_worker_dsn: str,
) -> None:
    await _assert_worker_login(capability_worker_dsn)
    org_id, agent_id = uuid4(), uuid4()
    await _seed_org(owner_factory, org_id)
    async with owner_factory() as session, session.begin():
        await session.execute(
            _sql(
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

    ledger = _pinned_ledger(worker_factory)
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
    await _assert_worker_login(capability_worker_dsn)

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
                await session.execute(_sql("SELECT current_user"))
            ).scalar_one() == "ibex_app"
        # Same pooled connection; SET LOCAL must have been rolled back.
        async with factory() as session:
            assert (
                await session.execute(_sql("SELECT current_user"))
            ).scalar_one() == "ibex_worker"
    finally:
        await engine.dispose()
