"""Unit tests for billing reconcile / spent rollup."""

from __future__ import annotations

import asyncio
from typing import Any

from app.tasks.billing_reconcile import (
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


def test_run_budget_spent_rollup_updates_spent() -> None:
    class FakeCH:
        def query_rows(self, sql: str) -> list[dict[str, Any]]:
            assert "usage_facts" in sql
            return [{"org_id": "11111111-1111-1111-1111-111111111111", "spent_cents": 4200}]

    class FakePG:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        async def update_spent(self, org_id: str, spent_cents: int) -> int:
            self.calls.append((org_id, spent_cents))
            return 1

    pg = FakePG()
    out = asyncio.run(run_budget_spent_rollup(querier=FakeCH(), updater=pg))
    assert out["status"] == "ok"
    assert out["orgs"] == 1
    assert out["periods_updated"] == 1
    assert pg.calls == [("11111111-1111-1111-1111-111111111111", 4200)]
