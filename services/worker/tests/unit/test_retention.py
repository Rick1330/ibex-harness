"""Unit tests for the P1-21 / P2-12 / P2-15 retention sweep.

Two properties matter more than the counts: the sweep never issues row-level
DML against a tenant table (its cross-tenant reach is the definer's), and it
never removes a live idempotency claim.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import retention
from app.config import Settings
from app.retention import (
    ClickHouseUsageFactsPartitions,
    NoopUsageFactsPartitions,
    RetentionPolicy,
    RetentionReport,
    SqlAlchemyRetentionStore,
    month_cutoff,
    partitions_to_drop,
    run_retention_sweep,
)
from app.tasks import maintenance

_NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


def _policy(**overrides: Any) -> RetentionPolicy:
    values: dict[str, Any] = {
        "scrub_after": timedelta(days=7),
        "delete_after": timedelta(days=30),
        "ledger_after": timedelta(hours=24),
        "keep_months": 13,
    }
    values.update(overrides)
    return RetentionPolicy(**values)


class _FakeStore:
    """Records the cutoffs and applies the windows the way the SQL does."""

    def __init__(
        self, *, tasks: list[datetime] | None = None, ledger: list[datetime] | None = None
    ):
        self.tasks = tasks or []
        self.ledger = ledger or []
        self.calls: list[tuple[str, datetime]] = []
        self.scrubbed: set[int] = set()

    async def scrub_failed_tasks(self, before: datetime) -> int:
        self.calls.append(("scrub", before))
        fresh = [
            index
            for index, failed_at in enumerate(self.tasks)
            if failed_at < before and index not in self.scrubbed
        ]
        self.scrubbed.update(fresh)
        return len(fresh)

    async def delete_failed_tasks(self, before: datetime) -> int:
        self.calls.append(("delete_tasks", before))
        keep = [failed_at for failed_at in self.tasks if not failed_at < before]
        removed = len(self.tasks) - len(keep)
        self.tasks = keep
        return removed

    async def delete_finalized_ledger(self, before: datetime) -> int:
        self.calls.append(("delete_ledger", before))
        keep = [updated_at for updated_at in self.ledger if not updated_at < before]
        removed = len(self.ledger) - len(keep)
        self.ledger = keep
        return removed


class _FakePartitions:
    def __init__(self, months: list[str]) -> None:
        self.months = months
        self.dropped: list[str] = []

    def list_months(self) -> list[str]:
        return list(self.months)

    def drop_month(self, month: str) -> None:
        # ClickHouse removes the partition, so a later listing no longer sees it.
        self.dropped.append(month)
        self.months = [known for known in self.months if known != month]


def _sweep(store: _FakeStore, partitions: _FakePartitions, policy: RetentionPolicy | None = None):
    return asyncio.run(
        run_retention_sweep(
            store=store,
            partitions=partitions,
            policy=policy or _policy(),
            now=_NOW,
        )
    )


def test_month_cutoff_counts_calendar_months() -> None:
    assert month_cutoff(_NOW, 13) == "202510"
    assert month_cutoff(_NOW, 1) == "202610"
    assert month_cutoff(_NOW, 0) == "202611"


def test_month_cutoff_crosses_a_year_boundary() -> None:
    assert month_cutoff(datetime(2026, 1, 15, tzinfo=UTC), 13) == "202412"
    assert month_cutoff(datetime(2026, 3, 1, tzinfo=UTC), 1) == "202602"


@pytest.mark.parametrize("keep_months", [-1, 100_000])
def test_month_cutoff_refuses_an_impossible_window(keep_months: int) -> None:
    with pytest.raises(ValueError, match="retention window|non-negative"):
        month_cutoff(_NOW, keep_months)


def test_partitions_to_drop_keeps_the_boundary_month() -> None:
    assert partitions_to_drop(["202509", "202510", "202511"], "202510") == ["202509"]
    assert partitions_to_drop(["202611"], "202510") == []


def test_partitions_to_drop_refuses_an_unknown_id() -> None:
    with pytest.raises(ValueError, match="unexpected usage_facts partition id"):
        partitions_to_drop(["2025-10"], "202510")


def test_sweep_applies_every_window_at_its_own_cutoff() -> None:
    store = _FakeStore(
        tasks=[_NOW - timedelta(days=8), _NOW - timedelta(days=31)],
        ledger=[_NOW - timedelta(hours=25)],
    )
    partitions = _FakePartitions(["202509", "202510", "202511"])

    report = _sweep(store, partitions)

    assert store.calls == [
        ("scrub", _NOW - timedelta(days=7)),
        ("delete_tasks", _NOW - timedelta(days=30)),
        ("delete_ledger", _NOW - timedelta(hours=24)),
    ]
    # The 8-day row is scrubbed and still present; the 31-day row is gone.
    assert report.scrubbed == 2
    assert report.deleted_tasks == 1
    assert len(store.tasks) == 1
    assert report.deleted_ledger == 1
    assert partitions.dropped == ["202509"]


def test_sweep_runs_the_partition_window_without_a_store() -> None:
    """No PostgreSQL DSN means no Postgres window, not no sweep at all."""
    partitions = _FakePartitions(["202509", "202511"])

    report = asyncio.run(
        run_retention_sweep(store=None, partitions=partitions, policy=_policy(), now=_NOW)
    )

    assert report.scrubbed == 0
    assert report.deleted_tasks == 0
    assert report.deleted_ledger == 0
    assert partitions.dropped == ["202509"]


def test_sweep_reports_nothing_dropped_when_no_partition_is_old_enough() -> None:
    report = _sweep(_FakeStore(), _FakePartitions(["202510", "202511"]))
    assert report.dropped_months == ()


def test_sweep_is_idempotent_on_a_second_run() -> None:
    store = _FakeStore(
        tasks=[_NOW - timedelta(days=8), _NOW - timedelta(days=31)],
        ledger=[_NOW - timedelta(hours=25)],
    )
    partitions = _FakePartitions(["202509"])
    first = _sweep(store, partitions)
    second = _sweep(store, partitions)

    assert first.scrubbed == 2
    assert second.scrubbed == 0
    assert second.deleted_tasks == 0
    assert second.deleted_ledger == 0
    # The partition is already gone; ClickHouse would fail on a second drop, so
    # the second run must not select it again from a fresh listing.
    assert partitions.dropped == ["202509"]
    assert (
        store.calls
        == [
            ("scrub", _NOW - timedelta(days=7)),
            ("delete_tasks", _NOW - timedelta(days=30)),
            ("delete_ledger", _NOW - timedelta(hours=24)),
        ]
        * 2
    )


def test_sweep_scrubs_before_it_deletes() -> None:
    store = _FakeStore(tasks=[_NOW - timedelta(days=31)])
    _sweep(store, _FakePartitions([]))
    assert [name for name, _ in store.calls][:2] == ["scrub", "delete_tasks"]


def test_sweep_issues_no_row_level_dml() -> None:
    """The only SQL the sweep sends is a call to a definer function.

    A row-level DELETE or UPDATE from the worker would need an org predicate it
    does not have and must not be given; ClickHouse is the only store where the
    sweep addresses a whole partition, and it never names a row.
    """
    statements = [
        retention._SCRUB_SQL,
        retention._DELETE_TASKS_SQL,
        retention._DELETE_LEDGER_SQL,
    ]
    for statement in statements:
        assert statement.startswith("SELECT ibex_core.retention_")
        for keyword in ("DELETE FROM", "UPDATE ", "INSERT INTO"):
            assert keyword not in statement.upper()


def test_report_serializes_for_the_task_result() -> None:
    report = RetentionReport(
        scrubbed=1, deleted_tasks=2, deleted_ledger=3, dropped_months=("202509",)
    )
    assert report.as_dict() == {
        "scrubbed": 1,
        "deleted_tasks": 2,
        "deleted_ledger": 3,
        "dropped_months": ["202509"],
    }


def test_noop_partitions_report_nothing_and_refuse_to_drop() -> None:
    noop = NoopUsageFactsPartitions()
    assert noop.list_months() == []
    with pytest.raises(AssertionError, match="no partition source"):
        noop.drop_month("202509")


class _Session:
    def __init__(self, value: int = 0) -> None:
        self.value = value
        self.executed: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, statement: Any, params: dict[str, Any]) -> Any:
        self.executed.append((str(statement), params))
        return SimpleNamespace(scalar_one=lambda: self.value)


def _store_with_session(session: _Session) -> tuple[SqlAlchemyRetentionStore, Any]:
    class _Ctx:
        async def __aenter__(self) -> _Session:
            return session

        async def __aexit__(self, *_args: object) -> None:
            return None

    return SqlAlchemyRetentionStore("postgresql+asyncpg://ibex@localhost/ibex"), _Ctx()


@pytest.mark.parametrize(
    ("method", "statement"),
    [
        ("scrub_failed_tasks", retention._SCRUB_SQL),
        ("delete_failed_tasks", retention._DELETE_TASKS_SQL),
        ("delete_finalized_ledger", retention._DELETE_LEDGER_SQL),
    ],
)
def test_store_calls_the_definer_with_the_cutoff(method: str, statement: str) -> None:
    session = _Session(value=4)
    store, ctx = _store_with_session(session)
    cutoff = _NOW - timedelta(days=1)
    with patch("app.retention.session_unpinned", return_value=ctx):
        count = asyncio.run(getattr(store, method)(cutoff))
    assert count == 4
    assert session.executed == [(statement, {"before": cutoff})]


def test_store_disposes_its_engine() -> None:
    store, _ctx = _store_with_session(_Session())
    store._engine = AsyncMock()
    asyncio.run(store.aclose())
    store._engine.dispose.assert_awaited_once()


def _clickhouse(rows: list[dict[str, str]], *, status: int = 200, text: str = "") -> Any:
    body = text or "\n".join(json.dumps(row) for row in rows)
    client = MagicMock()
    client.post.return_value = SimpleNamespace(status_code=status, text=body)
    return client


def test_clickhouse_lists_partitions_from_system_parts() -> None:
    client = _clickhouse([{"month": "202510"}, {"month": "202509"}])
    source = ClickHouseUsageFactsPartitions("http://localhost:8124/", client=client)

    assert source.list_months() == ["202509", "202510"]
    sql = client.post.call_args.kwargs["params"]["query"]
    assert "system.parts" in sql
    assert "database = 'ibex'" in sql
    assert "table = 'usage_facts'" in sql
    assert "active" in sql


def test_clickhouse_skips_blank_lines() -> None:
    client = _clickhouse([], text='{"month": "202509"}\n\n')
    source = ClickHouseUsageFactsPartitions("http://localhost:8124/", client=client)
    assert source.list_months() == ["202509"]


@pytest.mark.parametrize("payload", [{"month": "2025-09"}, {"other": "x"}])
def test_clickhouse_refuses_an_unexpected_partition_id(payload: dict[str, str]) -> None:
    client = _clickhouse([payload])
    source = ClickHouseUsageFactsPartitions("http://localhost:8124/", client=client)
    with pytest.raises(ValueError, match="unexpected usage_facts partition id"):
        source.list_months()


def test_clickhouse_drops_one_partition_by_id() -> None:
    client = _clickhouse([])
    source = ClickHouseUsageFactsPartitions("http://localhost:8124/", client=client)

    source.drop_month("202509")

    assert client.post.call_args.kwargs["params"]["query"] == (
        "ALTER TABLE ibex.usage_facts DROP PARTITION ID '202509'"
    )


def test_clickhouse_refuses_to_drop_an_unvalidated_id() -> None:
    client = _clickhouse([])
    source = ClickHouseUsageFactsPartitions("http://localhost:8124/", client=client)
    with pytest.raises(ValueError, match="unexpected usage_facts partition id"):
        source.drop_month("202509; DROP TABLE ibex.usage_facts")
    client.post.assert_not_called()


@pytest.mark.parametrize("failure", ["status", "transport"])
def test_clickhouse_maps_a_failure_to_oserror(failure: str) -> None:
    import httpx

    if failure == "status":
        client = _clickhouse([], status=500)
    else:
        client = MagicMock()
        client.post.side_effect = httpx.ConnectError("down")
    source = ClickHouseUsageFactsPartitions("http://localhost:8124/", client=client)
    with pytest.raises(OSError, match="clickhouse retention"):
        source.list_months()


def test_policy_reads_the_four_configured_windows() -> None:
    settings = Settings(
        failed_tasks_scrub_days=3,
        failed_tasks_retention_days=40,
        idempotency_ledger_retention_hours=12,
        usage_facts_retention_months=6,
    )
    policy = RetentionPolicy.from_settings(settings)
    assert policy == RetentionPolicy(
        scrub_after=timedelta(days=3),
        delete_after=timedelta(days=40),
        ledger_after=timedelta(hours=12),
        keep_months=6,
    )


def test_config_defaults_match_the_recorded_windows() -> None:
    settings = Settings()
    assert settings.failed_tasks_scrub_days == 7
    assert settings.failed_tasks_retention_days == 30
    assert settings.idempotency_ledger_retention_hours == 24
    assert settings.usage_facts_retention_months == 13


def test_config_refuses_a_scrub_window_past_the_retention_window() -> None:
    with pytest.raises(ValueError, match="failed_tasks_scrub_days"):
        Settings(failed_tasks_scrub_days=30, failed_tasks_retention_days=30)


def _task_settings(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "database_url": "postgresql+asyncpg://ibex@localhost/ibex",
        "clickhouse_dsn": "http://localhost:8124/",
        "failed_tasks_scrub_days": 7,
        "failed_tasks_retention_days": 30,
        "idempotency_ledger_retention_hours": 24,
        "usage_facts_retention_months": 13,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_retention_sweep_task_skips_without_a_database_url() -> None:
    settings = _task_settings(database_url=None, clickhouse_dsn=None)
    with patch.object(maintenance, "get_settings", return_value=settings):
        result = maintenance.retention_sweep()
    assert result == {
        "status": "skipped",
        "reason": "missing_dsn",
        "skipped": ["postgres", "clickhouse"],
    }


def test_retention_sweep_task_runs_clickhouse_without_postgres() -> None:
    """Partition cleanup needs no PostgreSQL connection, so an absent DSN must not skip it."""
    report = RetentionReport(
        scrubbed=0, deleted_tasks=0, deleted_ledger=0, dropped_months=("202509",)
    )
    sweep = AsyncMock(return_value=report)
    with (
        patch.object(
            maintenance,
            "get_settings",
            return_value=_task_settings(database_url=None),
        ),
        patch.object(maintenance, "SqlAlchemyRetentionStore") as store_cls,
        patch.object(maintenance, "run_retention_sweep", sweep),
    ):
        result = maintenance.retention_sweep()

    store_cls.assert_not_called()
    assert sweep.await_args.kwargs["store"] is None
    assert isinstance(sweep.await_args.kwargs["partitions"], ClickHouseUsageFactsPartitions)
    assert result == {
        "status": "ok",
        "scrubbed": 0,
        "deleted_tasks": 0,
        "deleted_ledger": 0,
        "dropped_months": ["202509"],
        "skipped": ["postgres"],
    }


def test_retention_sweep_task_runs_postgres_without_clickhouse() -> None:
    store = MagicMock()
    store.aclose = AsyncMock()
    report = RetentionReport(scrubbed=1, deleted_tasks=0, deleted_ledger=0, dropped_months=())
    with (
        patch.object(
            maintenance,
            "get_settings",
            return_value=_task_settings(clickhouse_dsn=None),
        ),
        patch.object(maintenance, "SqlAlchemyRetentionStore", return_value=store),
        patch.object(maintenance, "run_retention_sweep", AsyncMock(return_value=report)),
    ):
        result = maintenance.retention_sweep()

    assert result["status"] == "ok"
    assert result["skipped"] == ["clickhouse"]
    store.aclose.assert_awaited_once()


def test_retention_sweep_task_uses_one_event_loop_for_the_sweep_and_the_dispose() -> None:
    """The pool is bound to its loop: the dispose must run inside the loop that used it."""
    store = MagicMock()
    store.aclose = AsyncMock()
    report = RetentionReport(scrubbed=0, deleted_tasks=0, deleted_ledger=0, dropped_months=())
    real_run = asyncio.run
    coroutines: list[Any] = []

    def _counting_run(coro: Any) -> Any:
        coroutines.append(coro)
        return real_run(coro)

    with (
        patch.object(maintenance, "get_settings", return_value=_task_settings()),
        patch.object(maintenance, "SqlAlchemyRetentionStore", return_value=store),
        patch.object(maintenance, "run_retention_sweep", AsyncMock(return_value=report)),
        patch.object(maintenance.asyncio, "run", _counting_run),
    ):
        maintenance.retention_sweep()

    assert len(coroutines) == 1
    store.aclose.assert_awaited_once()


def test_retention_sweep_task_runs_both_stores() -> None:
    store = MagicMock()
    store.aclose = AsyncMock()
    report = RetentionReport(
        scrubbed=2, deleted_tasks=1, deleted_ledger=1, dropped_months=("202509",)
    )
    with (
        patch.object(maintenance, "get_settings", return_value=_task_settings()),
        patch.object(maintenance, "SqlAlchemyRetentionStore", return_value=store),
        patch.object(maintenance, "run_retention_sweep", AsyncMock(return_value=report)),
    ):
        result = maintenance.retention_sweep()

    assert result == {
        "status": "ok",
        "scrubbed": 2,
        "deleted_tasks": 1,
        "deleted_ledger": 1,
        "dropped_months": ["202509"],
        "skipped": [],
    }
    store.aclose.assert_awaited_once()


def test_retention_sweep_task_closes_the_store_when_the_sweep_raises() -> None:
    store = MagicMock()
    store.aclose = AsyncMock()
    with (
        patch.object(maintenance, "get_settings", return_value=_task_settings()),
        patch.object(maintenance, "SqlAlchemyRetentionStore", return_value=store),
        patch.object(
            maintenance, "run_retention_sweep", AsyncMock(side_effect=OSError("clickhouse down"))
        ),
        pytest.raises(OSError),
    ):
        maintenance.retention_sweep()
    store.aclose.assert_awaited_once()


def test_retention_sweep_task_skips_clickhouse_when_it_is_unconfigured() -> None:
    store = MagicMock()
    store.aclose = AsyncMock()
    report = RetentionReport(scrubbed=0, deleted_tasks=0, deleted_ledger=0, dropped_months=())
    sweep = AsyncMock(return_value=report)
    with (
        patch.object(maintenance, "get_settings", return_value=_task_settings(clickhouse_dsn=None)),
        patch.object(maintenance, "SqlAlchemyRetentionStore", return_value=store),
        patch.object(maintenance, "run_retention_sweep", sweep),
    ):
        result = maintenance.retention_sweep()

    assert result["status"] == "ok"
    assert result["skipped"] == ["clickhouse"]
    assert isinstance(sweep.await_args.kwargs["partitions"], NoopUsageFactsPartitions)
