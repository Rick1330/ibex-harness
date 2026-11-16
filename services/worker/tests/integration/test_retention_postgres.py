"""Real PostgreSQL + ClickHouse retention windows (P1-21 / P2-12 / P2-15).

The unit tests prove the cutoffs and the report. These prove the three things
only a real store can: the definer functions delete and scrub what the window
says as the ``ibex_worker`` login (which holds no grant on either table), a live
idempotency claim survives a sweep that removes a finalized one, and a whole
ClickHouse partition disappears while the current month's stays.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.db import create_engine
from app.extraction.clickhouse_traces import _http_endpoint
from app.retention import (
    ClickHouseUsageFactsPartitions,
    NoopUsageFactsPartitions,
    RetentionPolicy,
    SqlAlchemyRetentionStore,
    run_retention_sweep,
)

pytestmark = pytest.mark.integration

_POLICY = RetentionPolicy(
    scrub_after=timedelta(days=7),
    delete_after=timedelta(days=30),
    ledger_after=timedelta(hours=24),
    keep_months=13,
)
_SCRUBBED = "[scrubbed]"


def _sql(statement: str):
    return text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        statement
    )


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed_dead_letter(
    factory: async_sessionmaker, *, task_id: str, failed_at: datetime
) -> str:
    async with factory() as session, session.begin():
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_core.failed_tasks
                    (task_name, task_id, args, kwargs, exception_type,
                     exception_message, traceback, retry_count, failed_at)
                VALUES
                    ('ibex.worker.test.retention', :task_id,
                     '["secret-arg"]'::jsonb, '{"token": "secret"}'::jsonb,
                     'RuntimeError', 'boom: secret payload', 'traceback: secret', 1, :failed_at)
                """
            ),
            {"task_id": task_id, "failed_at": failed_at},
        )
    return task_id


async def _dead_letter(factory: async_sessionmaker, task_id: str) -> dict[str, object] | None:
    async with factory() as session:
        row = (
            (
                await session.execute(
                    _sql(
                        "SELECT args, kwargs, exception_message, traceback "
                        "FROM ibex_core.failed_tasks WHERE task_id = :task_id"
                    ),
                    {"task_id": task_id},
                )
            )
            .mappings()
            .first()
        )
    return dict(row) if row is not None else None


async def _seed_org_agent(factory: async_sessionmaker) -> tuple[UUID, UUID]:
    org_id, agent_id = uuid4(), uuid4()
    async with factory() as session, session.begin():
        await session.execute(
            _sql("INSERT INTO ibex_core.organizations (id, name, slug) VALUES (:id, :name, :slug)"),
            {
                "id": org_id,
                "name": f"Retention {org_id.hex[:8]}",
                "slug": f"retention-{org_id.hex[:12]}",
            },
        )
        await session.execute(
            _sql(
                "INSERT INTO ibex_core.agents (id, org_id, name, slug) "
                "VALUES (:id, :org_id, :name, :slug)"
            ),
            {
                "id": agent_id,
                "org_id": org_id,
                "name": "Retention agent",
                "slug": f"retention-agent-{agent_id.hex[:12]}",
            },
        )
    return org_id, agent_id


@dataclass(frozen=True, slots=True)
class _LedgerSeed:
    org_id: UUID
    agent_id: UUID
    key: str
    state: str
    updated_at: datetime


async def _seed_ledger(factory: async_sessionmaker, seed: _LedgerSeed) -> None:
    finalized = seed.state == "finalized"
    async with factory() as session, session.begin():
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_core.idempotency_ledger
                    (organization_id, agent_id, dedupe_key, request_hash, state,
                     status_code, response_payload, lease_expires_at, updated_at)
                VALUES
                    (:org_id, :agent_id, :key, :hash, :state,
                     :status_code, :payload, :lease, :updated_at)
                """
            ),
            {
                "org_id": seed.org_id,
                "agent_id": seed.agent_id,
                "key": seed.key,
                "hash": "c" * 64,
                "state": seed.state,
                "status_code": 202 if finalized else None,
                "payload": b'{"ok":true}' if finalized else None,
                "lease": None if finalized else _now() + timedelta(minutes=5),
                "updated_at": seed.updated_at,
            },
        )


async def _ledger_states(factory: async_sessionmaker, org_id: UUID) -> dict[str, str]:
    async with factory() as session:
        rows = (
            await session.execute(
                _sql(
                    "SELECT dedupe_key, state FROM ibex_core.idempotency_ledger "
                    "WHERE organization_id = :org_id"
                ),
                {"org_id": org_id},
            )
        ).fetchall()
    return {str(row.dedupe_key): str(row.state) for row in rows}


async def _delete_seed(factory: async_sessionmaker, org_id: UUID, agent_id: UUID) -> None:
    async with factory() as session, session.begin():
        await session.execute(
            _sql("DELETE FROM ibex_core.idempotency_ledger WHERE organization_id = :org_id"),
            {"org_id": org_id},
        )
        await session.execute(
            _sql("DELETE FROM ibex_core.agents WHERE id = :id AND org_id = :org_id"),
            {"id": agent_id, "org_id": org_id},
        )
        await session.execute(
            _sql("DELETE FROM ibex_core.organizations WHERE id = :id"), {"id": org_id}
        )


def _store(capability_worker_dsn: str) -> SqlAlchemyRetentionStore:
    """The store as the worker runs it: the ``ibex_worker`` login, no role pin."""
    return SqlAlchemyRetentionStore(capability_worker_dsn)


async def test_failed_tasks_are_scrubbed_then_deleted_by_window(
    owner_factory: async_sessionmaker,
    capability_worker_dsn: str,
    truncate_failed_tasks: None,
) -> None:
    now = _now()
    expired = await _seed_dead_letter(
        owner_factory, task_id="ret-31d", failed_at=now - timedelta(days=31)
    )
    scrubbable = await _seed_dead_letter(
        owner_factory, task_id="ret-8d", failed_at=now - timedelta(days=8)
    )
    fresh = await _seed_dead_letter(
        owner_factory, task_id="ret-1d", failed_at=now - timedelta(days=1)
    )
    store = _store(capability_worker_dsn)
    try:
        first = await run_retention_sweep(
            store=store, partitions=NoopUsageFactsPartitions(), policy=_POLICY
        )
        second = await run_retention_sweep(
            store=store, partitions=NoopUsageFactsPartitions(), policy=_POLICY
        )
    finally:
        await store.aclose()

    assert first.scrubbed == 2  # the 8-day and 31-day rows
    assert first.deleted_tasks == 1  # only the 31-day row
    # Reads go through the owner: ibex_worker holds no SELECT on the table, only
    # EXECUTE on the retention functions.
    assert await _dead_letter(owner_factory, expired) is None

    kept = await _dead_letter(owner_factory, scrubbable)
    assert kept is not None
    assert kept["args"] == []
    assert kept["kwargs"] == {}
    assert kept["exception_message"] == _SCRUBBED
    assert kept["traceback"] == _SCRUBBED

    untouched = await _dead_letter(owner_factory, fresh)
    assert untouched is not None
    assert untouched["exception_message"] == "boom: secret payload"
    assert "secret-arg" in json.dumps(untouched["args"])

    # Second run: nothing left to scrub or delete.
    assert (second.scrubbed, second.deleted_tasks, second.deleted_ledger) == (0, 0, 0)


async def test_a_live_idempotency_claim_survives_the_sweep(
    owner_factory: async_sessionmaker,
    capability_worker_dsn: str,
) -> None:
    now = _now()
    org_id, agent_id = await _seed_org_agent(owner_factory)
    for key, state, age in (
        ("finalized-old", "finalized", timedelta(hours=25)),
        ("claimed-old", "claimed", timedelta(hours=25)),
        ("finalized-fresh", "finalized", timedelta(hours=1)),
    ):
        await _seed_ledger(
            owner_factory,
            _LedgerSeed(
                org_id=org_id,
                agent_id=agent_id,
                key=key,
                state=state,
                updated_at=now - age,
            ),
        )
    store = _store(capability_worker_dsn)
    try:
        report = await run_retention_sweep(
            store=store, partitions=NoopUsageFactsPartitions(), policy=_POLICY
        )
        states = await _ledger_states(owner_factory, org_id)
    finally:
        await store.aclose()
        await _delete_seed(owner_factory, org_id, agent_id)

    # The ledger is shared with other suites, so the count is a lower bound; the
    # per-row assertions below are what this test actually pins.
    assert report.deleted_ledger >= 1
    # The live claim is still there even though it is older than the window: it
    # is in-flight work, and removing it would let a retry run twice.
    assert states == {"claimed-old": "claimed", "finalized-fresh": "finalized"}


def _insert_usage_fact(dsn: str, *, request_id: str, occurred_at: datetime) -> None:
    url, auth = _http_endpoint(dsn)
    row = {
        "request_id": request_id,
        "org_id": str(uuid4()),
        "agent_id": str(uuid4()),
        "provider": "openai",
        "model": "gpt-test",
        "input_tokens": 1,
        "output_tokens": 1,
        "total_tokens": 2,
        "estimated_cost_cents": 1,
        "rate_card_version": "v1",
        "occurred_at": occurred_at.strftime("%Y-%m-%d %H:%M:%S.000"),
    }
    resp = httpx.post(
        url,
        params={"query": "INSERT INTO ibex.usage_facts FORMAT JSONEachRow"},
        content=json.dumps(row),
        auth=auth,
        timeout=10.0,
    )
    assert resp.status_code < 400, resp.text


def _partition_months(dsn: str) -> list[str]:
    source = ClickHouseUsageFactsPartitions(dsn)
    return source.list_months()


def test_an_expired_usage_facts_partition_is_dropped_and_the_current_month_kept(
    capability_worker_dsn: str,
    clickhouse_http_dsn: str,
) -> None:
    now = _now()
    old_month = now - timedelta(days=420)  # comfortably past a 13-month window
    # Each run uses fresh ids; the rows carry a unique org and no assertion
    # aggregates over them, so they are left in place rather than scheduling a
    # ClickHouse mutation on a shared table.
    _insert_usage_fact(clickhouse_http_dsn, request_id=f"ret-old-{uuid4()}", occurred_at=old_month)
    _insert_usage_fact(clickhouse_http_dsn, request_id=f"ret-new-{uuid4()}", occurred_at=now)

    before = _partition_months(clickhouse_http_dsn)
    old_partition = old_month.strftime("%Y%m")
    assert old_partition in before

    async def _sweep_twice():
        # One loop and one engine: the pool binds connections to the loop that
        # created them, so a second asyncio.run would reuse a dead connection.
        store = _store(capability_worker_dsn)
        try:
            first = await run_retention_sweep(
                store=store,
                partitions=ClickHouseUsageFactsPartitions(clickhouse_http_dsn),
                policy=_POLICY,
            )
            second = await run_retention_sweep(
                store=store,
                partitions=ClickHouseUsageFactsPartitions(clickhouse_http_dsn),
                policy=_POLICY,
            )
        finally:
            await store.aclose()
        return first, second

    first, second = asyncio.run(_sweep_twice())

    assert old_partition in first.dropped_months
    assert old_partition not in _partition_months(clickhouse_http_dsn)
    assert now.strftime("%Y%m") in _partition_months(clickhouse_http_dsn)
    # The dropped partition is gone from the listing, so a second sweep has
    # nothing left to drop rather than failing on a missing partition.
    assert old_partition not in second.dropped_months


async def test_worker_cannot_reach_either_table_without_the_definer(
    capability_worker_dsn: str,
) -> None:
    """The sweep's cross-tenant reach is the function owner's, not a grant.

    Without the three functions the worker login has nothing to run these
    windows with: ``failed_tasks`` is INSERT-only for ``ibex_app`` and
    ``idempotency_ledger`` grants no DELETE to ``ibex_worker``. Granting it
    either would let a task reach every tenant's rows directly.
    """
    engine = create_engine(Settings(database_url=capability_worker_dsn))
    statements = (
        "SELECT 1 FROM ibex_core.failed_tasks LIMIT 1",
        "DELETE FROM ibex_core.idempotency_ledger WHERE false",
    )
    try:
        for statement in statements:
            with pytest.raises(DBAPIError) as caught:
                async with engine.begin() as conn:
                    await conn.execute(_sql(statement))
            assert "permission denied" in str(caught.value).lower(), statement
    finally:
        await engine.dispose()


async def test_the_functions_refuse_a_cutoff_in_the_future(
    capability_worker_dsn: str,
) -> None:
    """A future cutoff would purge rows the window has not reached."""
    store = _store(capability_worker_dsn)
    try:
        for window in (
            store.scrub_failed_tasks,
            store.delete_failed_tasks,
            store.delete_finalized_ledger,
        ):
            with pytest.raises(DBAPIError) as caught:
                await window(_now() + timedelta(days=1))
            assert "must be <= NOW()" in str(caught.value)
    finally:
        await store.aclose()
