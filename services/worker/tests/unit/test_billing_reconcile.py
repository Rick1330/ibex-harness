"""Unit tests for billing reconcile / spent rollup."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

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

    ch = FakeCH()
    pg = FakePG()
    out = asyncio.run(run_budget_spent_rollup(querier=ch, store=pg))
    assert out == {"status": "ok", "periods_updated": 1}
    assert ch.calls == [(period.org_id, start, end)]
    assert pg.updates == [(period.period_id, period.org_id, 4200)]


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

    out = asyncio.run(run_budget_spent_rollup(querier=FakeCH(), store=FakePG()))
    assert out["periods_updated"] == 1


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
