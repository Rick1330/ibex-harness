"""Positive controls for the worker billing and capture paths under a tenant pin.

A test that runs as the migration owner (``ibex``, superuser) bypasses RLS and
needs no role, so it cannot prove that ``SET LOCAL ROLE`` is doing anything.
Every test here connects as ``ibex_worker`` -- a ``NOINHERIT`` capability login
with no implicit tenant or purge privileges -- so a missing pin fails with
SQLSTATE 42501 instead of silently succeeding.

Red evidence for each test is recorded in the PR: removing the corresponding
``SET LOCAL ROLE`` makes it fail with ``permission denied``.

The seeded helpers and the shared premise live in ``tenant_pinning_support``;
sessions, dead letters and readiness are covered by
``test_worker_tenant_pinning_readiness_postgres``, and the erasure saga by
``test_worker_tenant_pinning_erasure_postgres``.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.budget_ledger as budget_ledger_module
from app.budget_ledger import (
    COMPLETENESS_COMPLETE,
    BudgetLedgerError,
    BudgetLedgerUnavailableError,
    _AsyncBudgetLedger,
)
from app.config import Settings
from app.db import session_unpinned
from app.tasks import capture_redaction
from app.tasks.billing_reconcile import SqlAlchemySpendStore
from tests.integration.tenant_pinning_support import (
    CapturePolicySeed,
    SessionEventSeed,
    SessionSeed,
    assert_worker_login,
    budget_request,
    count_rows,
    fetch_one,
    seed_capture_policy,
    seed_org,
    seed_period,
    seed_rate_card,
    seed_session,
    seed_session_event,
    seed_tenant_rows,
    sql_text,
    sqlstate,
)

pytestmark = pytest.mark.integration


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
    await seed_org(owner_factory, org_id)
    await seed_period(owner_factory, org_id, period_id)

    # The worker login cannot read the table directly (no grant, RLS forced).
    async with worker_factory() as session:
        with pytest.raises(ProgrammingError) as denied:
            await session.execute(sql_text("SELECT 1 FROM ibex_billing.budget_periods LIMIT 1"))
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
    """A pinned spend update moves its own row and cannot touch another org's."""
    await assert_worker_login(capability_worker_dsn)
    org_a, org_b = uuid4(), uuid4()
    period_a, period_b = uuid4(), uuid4()
    await seed_org(owner_factory, org_a)
    await seed_org(owner_factory, org_b)
    await seed_period(owner_factory, org_a, period_a)
    await seed_period(owner_factory, org_b, period_b)

    store = SqlAlchemySpendStore(capability_worker_dsn)
    try:
        await store.update_period_spent(str(period_a), str(org_a), 4200)
        # Wrong org for this period: the WHERE clause plus the org GUC must not
        # let a pinned transaction touch another tenant's row.
        await store.update_period_spent(str(period_b), str(org_a), 9999)
    finally:
        await store.aclose()

    assert (
        await count_rows(
            owner_factory,
            "SELECT spent_cents_cached FROM ibex_billing.budget_periods WHERE id = :id",
            id=period_a,
        )
        == 4200
    )
    assert (
        await count_rows(
            owner_factory,
            "SELECT spent_cents_cached FROM ibex_billing.budget_periods WHERE id = :id",
            id=period_b,
        )
        == 0
    )


# ---------------------------------------------------------------------------
# Budget ledger: capability probe + claim/finalize/release as the worker login.
# ---------------------------------------------------------------------------


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
    ledger = _AsyncBudgetLedger(worker_factory)
    with pytest.raises(BudgetLedgerError, match="budget reservation ledger is not ready"):
        await ledger.ping()


@pytest.mark.asyncio
async def test_budget_claim_finalize_release_pin_the_org_as_worker_login(
    owner_factory: async_sessionmaker[AsyncSession],
    worker_factory: async_sessionmaker[AsyncSession],
    capability_worker_dsn: str,
) -> None:
    """Claim, finalize, and release all run as the worker login under the org pin."""
    await assert_worker_login(capability_worker_dsn)
    org_id = uuid4()
    period_id = uuid4()
    card_id = uuid4()
    await seed_org(owner_factory, org_id)
    _, agent_id = await seed_tenant_rows(owner_factory, org_id, tag=org_id.hex[:8])
    await seed_period(owner_factory, org_id, period_id)
    await seed_rate_card(owner_factory, org_id, card_id)

    ledger = _AsyncBudgetLedger(worker_factory)
    claim = await ledger.claim(budget_request(org_id, agent_id, key="pinned-claim"))
    assert claim is not None
    assert claim.org_id == org_id
    assert (
        await ledger.finalize(claim, input_tokens=100, output_tokens=200)
        == COMPLETENESS_COMPLETE
    )

    released = await ledger.claim(budget_request(org_id, agent_id, key="pinned-release"))
    assert released is not None
    await ledger.release(released)

    state = (
        await fetch_one(
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
    """An unpinned claim fails 42501 instead of writing."""
    org_id = uuid4()
    await seed_org(owner_factory, org_id)
    _, agent_id = await seed_tenant_rows(owner_factory, org_id, tag=org_id.hex[:8])
    monkeypatch.setattr(
        budget_ledger_module,
        "session_as_app_org",
        lambda factory, _org: session_unpinned(factory),
    )
    ledger = _AsyncBudgetLedger(worker_factory)
    claim_request = budget_request(org_id, agent_id, key="unpinned-claim")
    with pytest.raises(BudgetLedgerUnavailableError) as err:
        await ledger.claim(claim_request)
    assert sqlstate(err.value.__cause__) == "42501", err.value


# ---------------------------------------------------------------------------
# Capture redaction: the policy read and the memory update as the worker login.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capture_redaction_reads_the_policy_as_worker_login(
    owner_factory: async_sessionmaker[AsyncSession],
    capability_worker_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The policy read succeeds on the pinned worker login (metadata-only path)."""
    await assert_worker_login(capability_worker_dsn)
    org_id = uuid4()
    await seed_org(owner_factory, org_id)
    await seed_capture_policy(owner_factory, CapturePolicySeed(org_id=org_id))
    monkeypatch.setattr(
        capture_redaction,
        "get_settings",
        lambda: Settings(database_url=capability_worker_dsn),
    )
    out = await capture_redaction._run(capture_redaction._CaptureJob(org_id=str(org_id)))
    assert out == {"status": "redacted", "mode": "metadata_only"}


@pytest.mark.asyncio
async def test_capture_redaction_agent_policy_wins_over_org_default_as_worker_login(
    owner_factory: async_sessionmaker[AsyncSession],
    capability_worker_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An agent-scoped row beats the org default even at a worse priority.

    This is the only case that binds a non-NULL ``agent_id`` into
    ``resolve_capture_mode``, so it exercises the ``CAST(:agent_id AS text)``
    binding and the ``agent_id IS NOT NULL`` ordering. The agent row is given
    the numerically larger (worse) priority on purpose: agent specificity, not
    priority alone, must select it.
    """
    await assert_worker_login(capability_worker_dsn)
    org_id = uuid4()
    await seed_org(owner_factory, org_id)
    _, agent_id = await seed_tenant_rows(owner_factory, org_id, tag=org_id.hex[:8])
    await seed_capture_policy(
        owner_factory,
        CapturePolicySeed(org_id=org_id, agent_id=None, mode="metadata_only", priority=0),
    )
    await seed_capture_policy(
        owner_factory,
        CapturePolicySeed(org_id=org_id, agent_id=agent_id, mode="redacted", priority=100),
    )
    monkeypatch.setattr(
        capture_redaction,
        "get_settings",
        lambda: Settings(database_url=capability_worker_dsn),
    )
    out = await capture_redaction._run(
        capture_redaction._CaptureJob(org_id=str(org_id), agent_id=str(agent_id))
    )
    assert out == {"status": "redacted", "mode": "redacted", "event_id": ""}


@pytest.mark.asyncio
async def test_capture_redaction_redacted_branch_persists_both_writes_as_worker_login(
    owner_factory: async_sessionmaker[AsyncSession],
    capability_worker_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ``redacted`` branch writes both columns through the pinned login.

    The metadata-only cases return before touching a row, so they cannot see a
    broken pin. This case seeds a real session event and forces ``redacted``:
    ``_persist_redacted`` rewrites ``data`` and ``_set_archived_to`` rewrites
    ``archived_to``, both inside ``session_as_app_org``. A pin that stopped
    binding the org would either fail 42501 or match zero rows (which
    ``_set_archived_to`` turns into an error), so the event cannot be lost
    quietly. The event id is passed as a string, exactly as Celery delivers it.
    """
    await assert_worker_login(capability_worker_dsn)
    org_id, session_id = uuid4(), uuid4()
    await seed_org(owner_factory, org_id)
    _, agent_id = await seed_tenant_rows(owner_factory, org_id, tag=org_id.hex[:8])
    await seed_session(
        owner_factory,
        SessionSeed(org_id=org_id, agent_id=agent_id, session_id=session_id),
    )
    await seed_capture_policy(
        owner_factory, CapturePolicySeed(org_id=org_id, mode="redacted")
    )
    payload = {"prompt": "secret", "content": "secret", "raw": "secret", "meta": "keep"}
    event_id = await seed_session_event(
        owner_factory,
        SessionEventSeed(org_id=org_id, session_id=session_id, data=payload),
    )
    archive_uri = f"s3://ibex-sessions/{org_id}/capture/redacted/{event_id}.json"
    uploaded: list[tuple[dict[str, object], str]] = []

    def fake_upload(_settings, _job, filtered, kind):
        uploaded.append((filtered, kind))
        return archive_uri

    monkeypatch.setattr(capture_redaction, "_put_archive_blob", fake_upload)
    monkeypatch.setattr(
        capture_redaction,
        "get_settings",
        lambda: Settings(database_url=capability_worker_dsn),
    )

    out = await capture_redaction._run(
        capture_redaction._CaptureJob(
            org_id=str(org_id), event_id=str(event_id), payload=payload
        )
    )

    # Celery serialises kwargs as JSON, so the task sees the id as a string.
    assert out == {
        "status": "redacted",
        "mode": "redacted",
        "event_id": str(event_id),
    }
    assert uploaded == [({"meta": "keep"}, "redacted")]
    row = await fetch_one(
        owner_factory,
        "SELECT data, archived_to FROM ibex_core.session_events"
        " WHERE id = :id AND org_id = :org",
        id=event_id,
        org=org_id,
    )
    assert row[0] == {"meta": "keep"}
    assert row[1] == archive_uri


@pytest.mark.asyncio
async def test_capture_redaction_rejects_non_numeric_event_id(
    owner_factory: async_sessionmaker[AsyncSession],
    capability_worker_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-numeric id fails with a clear ``ValueError``, not a driver ``DataError``.

    The column is ``bigint``; binding an arbitrary string would make asyncpg
    raise ``DataError`` after the transaction has started. The task must reject
    it at the boundary instead.
    """
    await assert_worker_login(capability_worker_dsn)
    org_id = uuid4()
    await seed_org(owner_factory, org_id)
    await seed_capture_policy(
        owner_factory, CapturePolicySeed(org_id=org_id, mode="redacted")
    )
    monkeypatch.setattr(
        capture_redaction,
        "get_settings",
        lambda: Settings(database_url=capability_worker_dsn),
    )

    with pytest.raises(ValueError, match="event_id must be a numeric string"):
        await capture_redaction._run(
            capture_redaction._CaptureJob(
                org_id=str(org_id), event_id="not-a-number", payload={"meta": "keep"}
            )
        )


@pytest.mark.asyncio
async def test_capture_redaction_without_the_pin_is_42501(
    owner_factory: async_sessionmaker[AsyncSession],
    capability_worker_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unpinned policy read fails 42501."""
    org_id = uuid4()
    await seed_org(owner_factory, org_id)
    await seed_capture_policy(owner_factory, CapturePolicySeed(org_id=org_id))
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
    assert sqlstate(err.value) == "42501", err.value
