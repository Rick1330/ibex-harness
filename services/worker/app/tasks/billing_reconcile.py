"""Billing reconciliation (4.P.4) — spent rollup from CH estimates; actuals wait on #859."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

import httpx
from sqlalchemy import text

from app.celery_app import celery_app
from app.config import get_settings
from app.db import create_engine, create_session_factory, session_as_service_account
from app.extraction.clickhouse_traces import _http_endpoint, shared_clickhouse_client
from app.task_names import TASK_BUDGET_SPENT_ROLLUP, TASK_RECONCILE_USAGE_ACTUALS
from app.tasks.base import IbexTask

logger = logging.getLogger(__name__)

_ROLLUP_SQL = """
SELECT
  toString(org_id) AS org_id,
  sum(estimated_cost_cents) AS spent_cents
FROM ibex.usage_facts
WHERE occurred_at >= now() - INTERVAL 40 DAY
GROUP BY org_id
FORMAT JSONEachRow
""".strip()


class ClickHouseQuerier(Protocol):
    def query_rows(self, sql: str) -> list[dict[str, Any]]: ...


class PostgresSpendUpdater(Protocol):
    async def update_spent(self, org_id: str, spent_cents: int) -> int: ...


class HttpClickHouseQuerier:
    def __init__(self, dsn: str, client: httpx.Client | None = None) -> None:
        self._dsn = dsn
        self._client = client or shared_clickhouse_client()

    def query_rows(self, sql: str) -> list[dict[str, Any]]:
        url, auth = _http_endpoint(self._dsn)
        resp = self._client.post(
            url,
            content=sql + "\n",
            headers={"Content-Type": "text/plain"},
            auth=auth,
            timeout=30.0,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"clickhouse rollup query failed: {resp.status_code}")
        import json

        rows: list[dict[str, Any]] = []
        for line in resp.text.splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows


class SqlAlchemySpendUpdater:
    def __init__(self, database_url: str) -> None:
        settings = get_settings()
        # Prefer explicit URL when provided by tests / callers.
        if database_url:
            from types import SimpleNamespace

            settings = SimpleNamespace(database_url=database_url)
        self._engine = create_engine(settings)  # type: ignore[arg-type]
        self._factory = create_session_factory(self._engine)

    async def update_spent(self, org_id: str, spent_cents: int) -> int:
        async with session_as_service_account(self._factory) as session:
            result = await session.execute(
                text(
                    """
                    UPDATE ibex_billing.budget_periods
                    SET spent_cents_cached = :spent,
                        updated_at = now()
                    WHERE org_id = CAST(:org_id AS uuid)
                      AND period_start <= now()
                      AND period_end > now()
                    """
                ),
                {"org_id": org_id, "spent": int(spent_cents)},
            )
            return int(result.rowcount or 0)

    async def aclose(self) -> None:
        await self._engine.dispose()


async def run_budget_spent_rollup(
    *,
    querier: ClickHouseQuerier,
    updater: PostgresSpendUpdater,
) -> dict[str, Any]:
    rows = querier.query_rows(_ROLLUP_SQL)
    updated = 0
    for row in rows:
        org_id = str(row.get("org_id") or "")
        if not org_id:
            continue
        spent = int(row.get("spent_cents") or 0)
        if spent < 0:
            continue
        updated += await updater.update_spent(org_id, spent)
    return {"status": "ok", "orgs": len(rows), "periods_updated": updated}


@celery_app.task(
    bind=True,
    base=IbexTask,
    name=TASK_RECONCILE_USAGE_ACTUALS,
    queue="maintenance",
)
def reconcile_usage_actuals(self: IbexTask, **kwargs: Any) -> dict[str, str]:
    """Select facts with null actual_cost_cents; no-op until invoice source exists (#859)."""
    del self, kwargs
    logger.info(
        "reconcile_usage_actuals skipped: no provider invoice source configured yet"
    )
    return {"status": "skipped", "reason": "no_invoice_source"}


@celery_app.task(
    bind=True,
    base=IbexTask,
    name=TASK_BUDGET_SPENT_ROLLUP,
    queue="maintenance",
)
def budget_spent_rollup(self: IbexTask, **kwargs: Any) -> dict[str, Any]:
    """Refresh budget_periods.spent_cents_cached from CH estimated_cost_cents sums."""
    del self, kwargs
    settings = get_settings()
    dsn = getattr(settings, "clickhouse_dsn", None)
    db_url = getattr(settings, "database_url", None)
    if not dsn or not db_url:
        logger.info("budget_spent_rollup skipped: missing clickhouse or postgres dsn")
        return {"status": "skipped", "reason": "missing_dsn"}
    querier = HttpClickHouseQuerier(dsn)
    updater = SqlAlchemySpendUpdater(db_url)
    try:
        return asyncio.run(run_budget_spent_rollup(querier=querier, updater=updater))
    finally:
        asyncio.run(updater.aclose())
