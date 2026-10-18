"""Real PostgreSQL tests for the worker budget reservation ledger (GAP-006).

These tests are skipped unless POSTGRES_DSN, POSTGRES_TEST_DSN, or
IBEX_WORKER_DATABASE_URL points at a migrated dedicated test database.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

import app.budget_ledger as ledger_module
from app.budget_ledger import (
    BudgetAdmissionDeniedError,
    BudgetClaimRequest,
    BudgetLedgerClaimClosedError,
    _AsyncBudgetLedger,
)
from app.config import Settings
from app.db import (
    create_engine,
    create_session_factory,
    session_as_service_account,
)

pytestmark = pytest.mark.integration

_LEASE_SECONDS = 900.0
_PRICES = [
    {
        "provider": "openai",
        "model_pattern": "gpt-4o*",
        "input_cents_per_1k": 10,
        "output_cents_per_1k": 30,
    }
]


def _sql(statement: str):
    return text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        statement
    )


@asynccontextmanager
async def _session_as_app_org(factory: async_sessionmaker, org_id: str):
    async with factory() as session, session.begin():
        await session.execute(_sql("SET LOCAL ROLE ibex_app"))
        await session.execute(
            _sql("SELECT set_config('app.current_org_id', :org_id, true)"),
            {"org_id": org_id},
        )
        await session.execute(_sql("SELECT set_config('app.is_service_account', 'false', true)"))
        yield session


@asynccontextmanager
async def _session_as_app_service_account(factory: async_sessionmaker):
    async with factory() as session, session.begin():
        await session.execute(_sql("SET LOCAL ROLE ibex_app"))
        await session.execute(_sql("SELECT set_config('app.is_service_account', 'true', true)"))
        yield session


@pytest_asyncio.fixture
async def pg_factory(migrated_postgres: str, monkeypatch: pytest.MonkeyPatch):
    engine: AsyncEngine = create_engine(Settings(database_url=migrated_postgres))
    factory = create_session_factory(engine)
    monkeypatch.setattr(ledger_module, "session_as_service_org", _session_as_app_org)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _seed_org_agent(factory: async_sessionmaker, org_id: UUID, agent_id: UUID) -> None:
    async with session_as_service_account(factory) as session:
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_core.organizations (id, name, slug)
                VALUES (:id, :name, :slug)
                """
            ),
            {"id": org_id, "name": f"Budget {org_id.hex[:8]}", "slug": f"budget-{org_id.hex[:12]}"},
        )
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_core.agents (id, org_id, name, slug)
                VALUES (:id, :org_id, :name, :slug)
                """
            ),
            {
                "id": agent_id,
                "org_id": org_id,
                "name": "Budget test agent",
                "slug": f"budget-agent-{agent_id.hex[:12]}",
            },
        )


async def _seed_budget_period(
    factory: async_sessionmaker,
    org_id: UUID,
    *,
    cap_cents: int,
    spent_cents: int = 0,
) -> UUID:
    period_id = uuid4()
    async with session_as_service_account(factory) as session:
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_billing.budget_periods
                    (id, org_id, period_start, period_end, cap_cents,
                     spent_cents_cached, enforcement_mode)
                VALUES (:id, :org_id, NOW() - interval '1 day', NOW() + interval '1 day',
                        :cap_cents, :spent_cents, 'hard_cap')
                """
            ),
            {
                "id": period_id,
                "org_id": org_id,
                "cap_cents": cap_cents,
                "spent_cents": spent_cents,
            },
        )
    return period_id


async def _seed_rate_card(factory: async_sessionmaker, org_id: UUID) -> None:
    card_id = uuid4()
    async with session_as_service_account(factory) as session:
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_billing.rate_cards (id, org_id, name, status)
                VALUES (:id, :org_id, :name, 'published')
                """
            ),
            {"id": card_id, "org_id": org_id, "name": f"card-{card_id.hex[:8]}"},
        )
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_billing.rate_card_versions
                    (rate_card_id, org_id, version, prices)
                VALUES (:card_id, :org_id, 1, CAST(:prices AS jsonb))
                """
            ),
            {"card_id": card_id, "org_id": org_id, "prices": json.dumps(_PRICES)},
        )


async def _delete_seed(factory: async_sessionmaker, org_id: UUID, agent_id: UUID) -> None:
    async with session_as_service_account(factory) as session:
        await session.execute(
            _sql("DELETE FROM ibex_core.budget_reservations WHERE organization_id = :org_id"),
            {"org_id": org_id},
        )
        await session.execute(
            _sql(
                """
                DELETE FROM ibex_billing.rate_card_versions v
                USING ibex_billing.rate_cards c
                WHERE v.rate_card_id = c.id AND c.org_id = :org_id
                """
            ),
            {"org_id": org_id},
        )
        await session.execute(
            _sql("DELETE FROM ibex_billing.rate_cards WHERE org_id = :org_id"),
            {"org_id": org_id},
        )
        await session.execute(
            _sql("DELETE FROM ibex_billing.budget_periods WHERE org_id = :org_id"),
            {"org_id": org_id},
        )
        await session.execute(
            _sql("DELETE FROM ibex_core.agents WHERE id = :id AND org_id = :org_id"),
            {"id": agent_id, "org_id": org_id},
        )
        await session.execute(
            _sql("DELETE FROM ibex_core.organizations WHERE id = :id"), {"id": org_id}
        )


async def _claim(ledger: _AsyncBudgetLedger, org_id: UUID, agent_id: UUID, **overrides):
    params = {
        "org_id": org_id,
        "agent_id": agent_id,
        "key": "extraction:key-1",
        "request_hash": "a" * 64,
        "provider": "openai",
        "model": "gpt-4o-mini",
        "input_tokens": 100,
        "output_tokens": 200,
    }
    params.update(overrides)
    return await ledger.claim(BudgetClaimRequest(**params))


async def _fetch_reservation(factory: async_sessionmaker, org_id: UUID, key: str) -> dict | None:
    async with session_as_service_account(factory) as session:
        result = await session.execute(
            _sql(
                """
                SELECT state, amount_estimated_cents, amount_final_cents,
                       finalized_completeness, price_input_cents_per_1k,
                       price_output_cents_per_1k, lease_expires_at, version
                FROM ibex_core.budget_reservations
                WHERE organization_id = :org_id AND reservation_key = :key
                """
            ),
            {"org_id": org_id, "key": key},
        )
        row = result.mappings().first()
        return dict(row) if row is not None else None


async def _publish_rate_card_version(
    factory: async_sessionmaker, org_id: UUID, *, prices: list[dict]
) -> None:
    async with session_as_service_account(factory) as session:
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_billing.rate_card_versions
                    (rate_card_id, org_id, version, prices)
                SELECT id, org_id, 2, CAST(:prices AS jsonb)
                FROM ibex_billing.rate_cards
                WHERE org_id = :org_id AND status = 'published'
                """
            ),
            {"org_id": org_id, "prices": json.dumps(prices)},
        )


async def _expire_lease(factory: async_sessionmaker, org_id: UUID, key: str) -> None:
    # created_at moves with the lease to satisfy the lease > created_at invariant.
    async with session_as_service_account(factory) as session:
        await session.execute(
            _sql(
                """
                UPDATE ibex_core.budget_reservations
                SET lease_expires_at = NOW() - interval '2 hours',
                    created_at = NOW() - interval '3 hours'
                WHERE organization_id = :org_id AND reservation_key = :key
                """
            ),
            {"org_id": org_id, "key": key},
        )


async def _seed_full_org(factory: async_sessionmaker, *, cap_cents: int, spent_cents: int = 0):
    org_id, agent_id = uuid4(), uuid4()
    await _seed_org_agent(factory, org_id, agent_id)
    await _seed_budget_period(factory, org_id, cap_cents=cap_cents, spent_cents=spent_cents)
    await _seed_rate_card(factory, org_id)
    return org_id, agent_id


@pytest.mark.asyncio
async def test_claim_no_hard_cap_returns_none(pg_factory) -> None:
    org_id, agent_id = uuid4(), uuid4()
    await _seed_org_agent(pg_factory, org_id, agent_id)
    try:
        ledger = _AsyncBudgetLedger(pg_factory, lease_seconds=_LEASE_SECONDS)
        assert await _claim(ledger, org_id, agent_id) is None
        assert await _fetch_reservation(pg_factory, org_id, "extraction:key-1") is None
    finally:
        await _delete_seed(pg_factory, org_id, agent_id)


@pytest.mark.asyncio
async def test_claim_exceeded_against_spent_cache(pg_factory) -> None:
    org_id, agent_id = uuid4(), uuid4()
    await _seed_org_agent(pg_factory, org_id, agent_id)
    await _seed_budget_period(pg_factory, org_id, cap_cents=5, spent_cents=5)
    await _seed_rate_card(pg_factory, org_id)
    try:
        ledger = _AsyncBudgetLedger(pg_factory, lease_seconds=_LEASE_SECONDS)
        with pytest.raises(BudgetAdmissionDeniedError) as err:
            await _claim(ledger, org_id, agent_id)
        assert err.value.kind == "exceeded"
        assert await _fetch_reservation(pg_factory, org_id, "extraction:key-1") is None
    finally:
        await _delete_seed(pg_factory, org_id, agent_id)


@pytest.mark.asyncio
async def test_claim_denied_without_rate_card_when_hard_cap(pg_factory) -> None:
    org_id, agent_id = uuid4(), uuid4()
    await _seed_org_agent(pg_factory, org_id, agent_id)
    await _seed_budget_period(pg_factory, org_id, cap_cents=10_000)
    try:
        ledger = _AsyncBudgetLedger(pg_factory, lease_seconds=_LEASE_SECONDS)
        with pytest.raises(BudgetAdmissionDeniedError) as err:
            await _claim(ledger, org_id, agent_id)
        assert err.value.kind == "no_rate_card"
    finally:
        await _delete_seed(pg_factory, org_id, agent_id)


@pytest.mark.asyncio
async def test_claim_finalize_replay_and_release_lifecycle(pg_factory) -> None:
    org_id, agent_id = await _seed_full_org(pg_factory, cap_cents=10_000)
    try:
        ledger = _AsyncBudgetLedger(pg_factory, lease_seconds=_LEASE_SECONDS)
        claim = await _claim(ledger, org_id, agent_id)
        assert claim is not None
        row = await _fetch_reservation(pg_factory, org_id, claim.key)
        assert row is not None
        assert row["state"] == "claimed"
        assert row["amount_estimated_cents"] == 7
        assert row["lease_expires_at"] is not None

        with pytest.raises(BudgetAdmissionDeniedError) as err:
            await _claim(ledger, org_id, agent_id)
        assert err.value.kind == "in_progress"

        assert (
            await ledger.finalize(claim, input_tokens=100, output_tokens=200) == "complete"
        )
        assert (
            await ledger.finalize(claim, input_tokens=100, output_tokens=200) == "complete"
        )
        row = await _fetch_reservation(pg_factory, org_id, claim.key)
        assert row is not None
        assert row["state"] == "finalized"
        assert row["amount_final_cents"] == 7
        assert row["finalized_completeness"] == "complete"
        assert row["lease_expires_at"] is None

        reclaimed = await _claim(ledger, org_id, agent_id)
        assert reclaimed is not None
        assert reclaimed.version > claim.version
        await ledger.release(reclaimed)
        row = await _fetch_reservation(pg_factory, org_id, claim.key)
        assert row is not None
        assert row["state"] == "released"
        await ledger.release(reclaimed)
    finally:
        await _delete_seed(pg_factory, org_id, agent_id)


@pytest.mark.asyncio
async def test_claim_finalize_estimated_without_usage(pg_factory) -> None:
    org_id, agent_id = await _seed_full_org(pg_factory, cap_cents=10_000)
    try:
        ledger = _AsyncBudgetLedger(pg_factory, lease_seconds=_LEASE_SECONDS)
        claim = await _claim(ledger, org_id, agent_id)
        assert claim is not None
        assert await ledger.finalize(claim, input_tokens=0, output_tokens=0) == "estimated"
        row = await _fetch_reservation(pg_factory, org_id, claim.key)
        assert row is not None
        assert row["state"] == "finalized"
        assert row["amount_final_cents"] == row["amount_estimated_cents"]
        assert row["finalized_completeness"] == "estimated"
    finally:
        await _delete_seed(pg_factory, org_id, agent_id)


@pytest.mark.asyncio
async def test_finalize_uses_claim_time_rates_after_repricing(pg_factory) -> None:
    org_id, agent_id = await _seed_full_org(pg_factory, cap_cents=10_000)
    try:
        ledger = _AsyncBudgetLedger(pg_factory, lease_seconds=_LEASE_SECONDS)
        claim = await _claim(ledger, org_id, agent_id)
        assert claim is not None
        row = await _fetch_reservation(pg_factory, org_id, claim.key)
        assert row is not None
        assert (row["price_input_cents_per_1k"], row["price_output_cents_per_1k"]) == (10, 30)

        await _publish_rate_card_version(
            pg_factory,
            org_id,
            prices=[
                {
                    "provider": "openai",
                    "model_pattern": "gpt-4o*",
                    "input_cents_per_1k": 100,
                    "output_cents_per_1k": 100,
                }
            ],
        )
        assert await ledger.finalize(claim, input_tokens=100, output_tokens=200) == "complete"
        assert await ledger.finalize(claim, input_tokens=100, output_tokens=200) == "complete"
        row = await _fetch_reservation(pg_factory, org_id, claim.key)
        assert row is not None
        assert row["amount_final_cents"] == 7
    finally:
        await _delete_seed(pg_factory, org_id, agent_id)


@pytest.mark.asyncio
async def test_terminal_replay_fenced_by_version(pg_factory) -> None:
    org_id, agent_id = await _seed_full_org(pg_factory, cap_cents=10_000)
    try:
        ledger = _AsyncBudgetLedger(pg_factory, lease_seconds=_LEASE_SECONDS)
        first = await _claim(ledger, org_id, agent_id)
        assert first is not None
        assert await ledger.finalize(first, input_tokens=100, output_tokens=200) == "complete"

        reclaimed = await _claim(ledger, org_id, agent_id)
        assert reclaimed is not None
        assert reclaimed.claim_id == first.claim_id
        assert reclaimed.version > first.version

        # The old owner's identical settlement must not replay against the newer owner.
        with pytest.raises(BudgetLedgerClaimClosedError):
            await ledger.finalize(first, input_tokens=100, output_tokens=200)

        await ledger.release(reclaimed)
        with pytest.raises(BudgetLedgerClaimClosedError):
            await ledger.release(first)
    finally:
        await _delete_seed(pg_factory, org_id, agent_id)


@pytest.mark.asyncio
async def test_sweep_leaves_fresh_reclaim_claimed(pg_factory) -> None:
    org_id, agent_id = await _seed_full_org(pg_factory, cap_cents=10_000)
    try:
        ledger = _AsyncBudgetLedger(pg_factory, lease_seconds=_LEASE_SECONDS)
        first = await _claim(ledger, org_id, agent_id)
        assert first is not None
        await _expire_lease(pg_factory, org_id, first.key)
        reclaimed = await _claim(ledger, org_id, agent_id)
        assert reclaimed is not None
        assert reclaimed.version == first.version + 1

        await ledger.expire_stale(grace_seconds=0, batch_limit=100)
        row = await _fetch_reservation(pg_factory, org_id, first.key)
        assert row is not None and row["state"] == "claimed"
    finally:
        await _delete_seed(pg_factory, org_id, agent_id)


@pytest.mark.asyncio
async def test_claim_conflict_on_hash_mismatch(pg_factory) -> None:
    org_id, agent_id = await _seed_full_org(pg_factory, cap_cents=10_000)
    try:
        ledger = _AsyncBudgetLedger(pg_factory, lease_seconds=_LEASE_SECONDS)
        assert await _claim(ledger, org_id, agent_id) is not None
        with pytest.raises(BudgetAdmissionDeniedError) as err:
            await _claim(ledger, org_id, agent_id, request_hash="b" * 64)
        assert err.value.kind == "conflict"
    finally:
        await _delete_seed(pg_factory, org_id, agent_id)


@pytest.mark.asyncio
async def test_expired_lease_reclaims_and_holds_bound_other_keys(pg_factory) -> None:
    org_id, agent_id = await _seed_full_org(pg_factory, cap_cents=7)
    try:
        ledger = _AsyncBudgetLedger(pg_factory, lease_seconds=_LEASE_SECONDS)
        first = await _claim(ledger, org_id, agent_id, key="extraction:key-1")
        assert first is not None
        with pytest.raises(BudgetAdmissionDeniedError) as err:
            await _claim(ledger, org_id, agent_id, key="extraction:key-2")
        assert err.value.kind == "exceeded"

        await _expire_lease(pg_factory, org_id, "extraction:key-1")
        third = await _claim(ledger, org_id, agent_id, key="extraction:key-2")
        assert third is not None
    finally:
        await _delete_seed(pg_factory, org_id, agent_id)


@pytest.mark.asyncio
async def test_stale_key_reclaims_after_expiry(pg_factory) -> None:
    org_id, agent_id = await _seed_full_org(pg_factory, cap_cents=10_000)
    try:
        ledger = _AsyncBudgetLedger(pg_factory, lease_seconds=_LEASE_SECONDS)
        first = await _claim(ledger, org_id, agent_id)
        assert first is not None
        await _expire_lease(pg_factory, org_id, first.key)
        second = await _claim(ledger, org_id, agent_id)
        assert second is not None
        assert second.claim_id == first.claim_id
        assert second.version == first.version + 1
    finally:
        await _delete_seed(pg_factory, org_id, agent_id)


@pytest.mark.asyncio
async def test_cross_tenant_isolation_and_service_account_sweep(
    pg_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_a, agent_a = await _seed_full_org(pg_factory, cap_cents=10_000)
    org_b, agent_b = await _seed_full_org(pg_factory, cap_cents=10_000)
    try:
        ledger = _AsyncBudgetLedger(pg_factory, lease_seconds=_LEASE_SECONDS)
        claim_a = await _claim(ledger, org_a, agent_a, key="extraction:shared")
        assert claim_a is not None

        async with _session_as_app_org(pg_factory, str(org_a)) as session:
            visible_a = (
                await session.execute(
                    _sql(
                        "SELECT count(*) FROM ibex_core.budget_reservations "
                        "WHERE organization_id IN (:org_a, :org_b)"
                    ),
                    {"org_a": org_a, "org_b": org_b},
                )
            ).scalar_one()
        async with _session_as_app_org(pg_factory, str(org_b)) as session:
            visible_b = (
                await session.execute(
                    _sql(
                        "SELECT count(*) FROM ibex_core.budget_reservations "
                        "WHERE organization_id IN (:org_a, :org_b)"
                    ),
                    {"org_a": org_a, "org_b": org_b},
                )
            ).scalar_one()
        assert visible_a == 1
        assert visible_b == 0

        claim_b = await _claim(ledger, org_b, agent_b, key="extraction:shared")
        assert claim_b is not None
        assert claim_b.org_id == org_b

        await _expire_lease(pg_factory, org_a, "extraction:shared")
        await _expire_lease(pg_factory, org_b, "extraction:shared")
        monkeypatch.setattr(
            ledger_module, "session_as_service_account", _session_as_app_service_account
        )
        expired = await ledger.expire_stale(grace_seconds=3600, batch_limit=100)
        assert expired >= 2
        row_a = await _fetch_reservation(pg_factory, org_a, "extraction:shared")
        row_b = await _fetch_reservation(pg_factory, org_b, "extraction:shared")
        assert row_a is not None and row_a["state"] == "expired"
        assert row_b is not None and row_b["state"] == "expired"
    finally:
        monkeypatch.undo()
        await _delete_seed(pg_factory, org_a, agent_a)
        await _delete_seed(pg_factory, org_b, agent_b)
