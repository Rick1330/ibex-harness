"""Unit tests for billing reconcile / spent rollup."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from redis.exceptions import RedisError

from app.tasks.billing_reconcile import (
    BudgetPeriodWindow,
    HttpClickHouseQuerier,
    budget_spent_rollup,
    reconcile_usage_actuals,
    run_budget_spent_rollup,
)


def test_reconcile_usage_actuals_skips() -> None:
    out = reconcile_usage_actuals.run()
    assert out["status"] == "skipped"
    assert out["reason"] == "no_invoice_source"


def test_budget_spent_rollup_skips_without_dsn(monkeypatch: Any) -> None:
    class _Settings:
        clickhouse_dsn = None
        database_url = None

    monkeypatch.setattr("app.tasks.billing_reconcile.get_settings", lambda: _Settings())
    out = budget_spent_rollup.run()
    assert out["status"] == "skipped"
    assert out["reason"] == "missing_dsn"


def test_run_budget_spent_rollup_period_scoped() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=60)
    period = BudgetPeriodWindow(
        period_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        org_id="11111111-1111-1111-1111-111111111111",
        period_start=start,
        period_end=end,
    )

    class FakeCH:
        def __init__(self) -> None:
            self.calls: list[tuple[str, datetime, datetime]] = []

        def sum_spent(
            self, *, org_id: str, period_start: datetime, period_end: datetime
        ) -> int:
            self.calls.append((org_id, period_start, period_end))
            return 4200

    class FakePG:
        def __init__(self) -> None:
            self.updates: list[tuple[str, str, int]] = []

        async def list_active_periods(self) -> list[BudgetPeriodWindow]:
            return [period]

        async def update_period_spent(self, period_id: str, org_id: str, spent_cents: int) -> None:
            self.updates.append((period_id, org_id, spent_cents))

    class FakeInv:
        def __init__(self) -> None:
            self.published: list[str] = []

        async def publish_budget_update(self, org_id: str) -> None:
            self.published.append(org_id)

    ch = FakeCH()
    pg = FakePG()
    inv = FakeInv()
    out = asyncio.run(run_budget_spent_rollup(querier=ch, store=pg, invalidator=inv))
    assert out == {"status": "ok", "periods_updated": 1}
    assert ch.calls == [(period.org_id, start, end)]
    assert pg.updates == [(period.period_id, period.org_id, 4200)]
    assert inv.published == [period.org_id]


def test_run_budget_spent_rollup_zero_spend_period() -> None:
    start = datetime.now(UTC) - timedelta(hours=1)
    end = start + timedelta(days=1)
    period = BudgetPeriodWindow(
        period_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        org_id="22222222-2222-2222-2222-222222222222",
        period_start=start,
        period_end=end,
    )

    class FakeCH:
        def sum_spent(self, **kwargs: Any) -> int:
            return 0

    class FakePG:
        def __init__(self) -> None:
            self.updates: list[int] = []

        async def list_active_periods(self) -> list[BudgetPeriodWindow]:
            return [period]

        async def update_period_spent(self, period_id: str, org_id: str, spent_cents: int) -> None:
            self.updates.append(spent_cents)

    pg = FakePG()
    out = asyncio.run(run_budget_spent_rollup(querier=FakeCH(), store=pg))
    assert out["periods_updated"] == 1
    assert pg.updates == [0]


def test_run_budget_spent_rollup_skips_invalidate_on_update_failure() -> None:
    period = BudgetPeriodWindow(
        period_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
        org_id="33333333-3333-3333-3333-333333333333",
        period_start=datetime.now(UTC),
        period_end=datetime.now(UTC) + timedelta(days=1),
    )

    class FakeCH:
        def sum_spent(self, **kwargs: Any) -> int:
            return 1

    class BoomPG:
        async def list_active_periods(self) -> list[BudgetPeriodWindow]:
            return [period]

        async def update_period_spent(self, period_id: str, org_id: str, spent_cents: int) -> None:
            raise RuntimeError("db down")

    class FakeInv:
        def __init__(self) -> None:
            self.published: list[str] = []

        async def publish_budget_update(self, org_id: str) -> None:
            self.published.append(org_id)

    inv = FakeInv()
    try:
        asyncio.run(run_budget_spent_rollup(querier=FakeCH(), store=BoomPG(), invalidator=inv))
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass
    assert inv.published == []


def test_http_clickhouse_querier_parses_spent() -> None:
    client = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.text = '{"spent_cents":"99"}\n'
    client.post.return_value = resp
    q = HttpClickHouseQuerier("http://localhost:8123", client=client)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=1)
    assert q.sum_spent(org_id="11111111-1111-1111-1111-111111111111", period_start=start, period_end=end) == 99
    params = client.post.call_args.kwargs["params"]
    assert params["param_org_id"] == "11111111-1111-1111-1111-111111111111"
    assert "{org_id:UUID}" in params["query"]
    assert "param_period_start" in params
    assert "param_period_end" in params
    assert "occurred_at >=" in params["query"]
    assert "occurred_at <" in params["query"]


def test_run_budget_spent_rollup_reraises_invalidate_failure() -> None:
    period = BudgetPeriodWindow(
        period_id="dddddddd-dddd-dddd-dddd-dddddddddddd",
        org_id="44444444-4444-4444-4444-444444444444",
        period_start=datetime.now(UTC),
        period_end=datetime.now(UTC) + timedelta(days=1),
    )

    class FakeCH:
        def sum_spent(self, **kwargs: Any) -> int:
            return 10

    class FakePG:
        async def list_active_periods(self) -> list[BudgetPeriodWindow]:
            return [period]

        async def update_period_spent(self, period_id: str, org_id: str, spent_cents: int) -> None:
            return None

    class BoomInv:
        async def publish_budget_update(self, org_id: str) -> None:
            raise RedisError("pubsub down")

    try:
        asyncio.run(
            run_budget_spent_rollup(querier=FakeCH(), store=FakePG(), invalidator=BoomInv())
        )
        raise AssertionError("expected RedisError")
    except RedisError:
        pass


def test_http_clickhouse_querier_error_status() -> None:
    client = MagicMock()
    resp = MagicMock()
    resp.status_code = 503
    resp.text = "unavailable"
    client.post.return_value = resp
    q = HttpClickHouseQuerier("http://localhost:8123", client=client)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=1)
    try:
        q.sum_spent(
            org_id="11111111-1111-1111-1111-111111111111",
            period_start=start,
            period_end=end,
        )
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "503" in str(exc)


def test_http_clickhouse_querier_skips_blank_lines() -> None:
    client = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.text = "\n\n{\"spent_cents\":7}\n\n"
    client.post.return_value = resp
    q = HttpClickHouseQuerier("http://localhost:8123", client=client)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    assert (
        q.sum_spent(
            org_id="11111111-1111-1111-1111-111111111111",
            period_start=start,
            period_end=start + timedelta(days=1),
        )
        == 7
    )


def test_fmt_ts_naive_and_aware() -> None:
    from app.tasks.billing_reconcile import _fmt_ts

    naive = datetime(2026, 1, 1, 12, 0, 0)
    assert _fmt_ts(naive).startswith("2026-01-01 12:00:00")
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert _fmt_ts(aware).startswith("2026-01-01 12:00:00")


@pytest.mark.asyncio
async def test_redis_budget_cache_invalidator_publish(monkeypatch: Any) -> None:
    from app.tasks.billing_reconcile import RedisBudgetCacheInvalidator

    published: list[tuple[str, str]] = []

    class FakeRedis:
        async def publish(self, channel: str, payload: str) -> int:
            published.append((channel, payload))
            return 1

        async def aclose(self) -> None:
            return None

    fake = FakeRedis()

    def _from_url(*args: Any, **kwargs: Any) -> FakeRedis:
        del args, kwargs
        return fake

    monkeypatch.setattr("redis.asyncio.Redis.from_url", _from_url)
    inv = RedisBudgetCacheInvalidator("redis://localhost:6379/0")
    await inv.publish_budget_update("11111111-1111-1111-1111-111111111111")
    assert published[0][0] == "budget_updates:11111111-1111-1111-1111-111111111111"
    assert "org_id" in published[0][1]
    await inv.aclose()


@pytest.mark.asyncio
async def test_noop_budget_cache_invalidator() -> None:
    from app.tasks.billing_reconcile import NoopBudgetCacheInvalidator

    await NoopBudgetCacheInvalidator().publish_budget_update("x")


def test_budget_spent_rollup_runs_with_deps(monkeypatch: Any) -> None:
    period = BudgetPeriodWindow(
        period_id="eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
        org_id="55555555-5555-5555-5555-555555555555",
        period_start=datetime.now(UTC),
        period_end=datetime.now(UTC) + timedelta(days=1),
    )

    class FakeCH:
        def sum_spent(self, **kwargs: Any) -> int:
            return 3

    class FakeStore:
        async def list_active_periods(self) -> list[BudgetPeriodWindow]:
            return [period]

        async def update_period_spent(self, period_id: str, org_id: str, spent_cents: int) -> None:
            return None

        async def aclose(self) -> None:
            return None

    class FakeInv:
        async def publish_budget_update(self, org_id: str) -> None:
            return None

        async def aclose(self) -> None:
            return None

    class _Settings:
        clickhouse_dsn = "http://localhost:8123"
        database_url = "postgresql+asyncpg://u:p@localhost/db"
        redis_url = "redis://localhost:6379/0"

    monkeypatch.setattr("app.tasks.billing_reconcile.get_settings", lambda: _Settings())
    monkeypatch.setattr(
        "app.tasks.billing_reconcile.HttpClickHouseQuerier", lambda dsn: FakeCH()
    )
    monkeypatch.setattr(
        "app.tasks.billing_reconcile.SqlAlchemySpendStore", lambda url: FakeStore()
    )
    monkeypatch.setattr(
        "app.tasks.billing_reconcile.RedisBudgetCacheInvalidator",
        lambda url: FakeInv(),
    )
    out = budget_spent_rollup.run()
    assert out["status"] == "ok"
    assert out["periods_updated"] == 1


def test_budget_spent_rollup_task_autoretry_configured() -> None:
    assert RedisError in budget_spent_rollup.autoretry_for
    assert OSError in budget_spent_rollup.autoretry_for
    assert RuntimeError in budget_spent_rollup.autoretry_for
    assert budget_spent_rollup.retry_backoff is True
    assert budget_spent_rollup.retry_jitter is True
