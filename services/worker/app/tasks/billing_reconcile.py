"""Billing reconciliation (4.P.4) — period-scoped spent rollup; actuals wait on #859."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import httpx
from redis.exceptions import RedisError
from sqlalchemy import text

from app.celery_app import celery_app
from app.config import get_settings
from app.db import create_engine, create_session_factory, session_as_service_account
from app.extraction.clickhouse_traces import _http_endpoint, shared_clickhouse_client
from app.task_names import TASK_BUDGET_SPENT_ROLLUP, TASK_RECONCILE_USAGE_ACTUALS
from app.tasks.base import IbexTask

logger = logging.getLogger(__name__)

_BUDGET_CHANNEL_PREFIX = "budget_updates:"
_BUDGET_EVENT_VERSION = 1
_REDIS_SOCKET_TIMEOUT_SECONDS = 1.0


class ClickHouseQueryError(Exception):
    """Transient ClickHouse HTTP failure during spent rollup."""


@dataclass(frozen=True, slots=True)
class BudgetPeriodWindow:
    period_id: str
    org_id: str
    period_start: datetime
    period_end: datetime


class ClickHouseQuerier(Protocol):
    def sum_spent(
        self, *, org_id: str, period_start: datetime, period_end: datetime
    ) -> int: ...


class PostgresSpendStore(Protocol):
    async def list_active_periods(self) -> list[BudgetPeriodWindow]: ...

    async def update_period_spent(self, period_id: str, org_id: str, spent_cents: int) -> None: ...


class BudgetCacheInvalidator(Protocol):
    async def publish_budget_update(self, org_id: str) -> None: ...


class NoopBudgetCacheInvalidator:
    async def publish_budget_update(self, org_id: str) -> None:
        del org_id
        await asyncio.sleep(0)


class RedisBudgetCacheInvalidator:
    """PUBLISH budget_updates:{org_id} after spent_cents_cached commits."""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            from redis.asyncio import Redis

            self._client = Redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=_REDIS_SOCKET_TIMEOUT_SECONDS,
                socket_timeout=_REDIS_SOCKET_TIMEOUT_SECONDS,
            )
        return self._client

    async def publish_budget_update(self, org_id: str) -> None:
        client = self._get_client()
        channel = f"{_BUDGET_CHANNEL_PREFIX}{org_id}"
        payload = json.dumps({"v": _BUDGET_EVENT_VERSION, "org_id": org_id})
        await client.publish(channel, payload)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class HttpClickHouseQuerier:
    def __init__(self, dsn: str, client: httpx.Client | None = None) -> None:
        self._dsn = dsn
        self._client = client or shared_clickhouse_client()

    def sum_spent(
        self, *, org_id: str, period_start: datetime, period_end: datetime
    ) -> int:
        # Explicit org_id required (ClickHouse has no RLS). Named params avoid B608.
        sql = (
            "SELECT coalesce(sum(estimated_cost_cents), 0) AS spent_cents "
            "FROM ibex.usage_facts "
            "WHERE org_id = {org_id:UUID} "
            "AND occurred_at >= {period_start:DateTime64(3, 'UTC')} "
            "AND occurred_at < {period_end:DateTime64(3, 'UTC')} "
            "FORMAT JSONEachRow"
        )
        url, auth = _http_endpoint(self._dsn)
        try:
            resp = self._client.post(
                url,
                params={
                    "query": sql,
                    "param_org_id": org_id,
                    "param_period_start": _fmt_ts(period_start),
                    "param_period_end": _fmt_ts(period_end),
                },
                auth=auth,
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            raise ClickHouseQueryError(f"clickhouse rollup transport failed: {exc}") from exc
        if resp.status_code >= 400:
            raise ClickHouseQueryError(f"clickhouse rollup query failed: {resp.status_code}")
        spent = 0
        for line in resp.text.splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            spent = int(row.get("spent_cents") or 0)
        return max(spent, 0)


class SqlAlchemySpendStore:
    def __init__(self, database_url: str) -> None:
        from types import SimpleNamespace

        settings = SimpleNamespace(database_url=database_url) if database_url else get_settings()
        self._engine = create_engine(settings)  # type: ignore[arg-type]
        self._factory = create_session_factory(self._engine)

    async def list_active_periods(self) -> list[BudgetPeriodWindow]:
        async with session_as_service_account(self._factory) as session:
            result = await session.execute(
                text(
                    """
                    SELECT id::text AS period_id, org_id::text AS org_id,
                           period_start, period_end
                    FROM ibex_billing.budget_periods
                    WHERE period_start <= now() AND period_end > now()
                    """
                )
            )
            rows = result.fetchall()
        return [
            BudgetPeriodWindow(
                period_id=str(r.period_id),
                org_id=str(r.org_id),
                period_start=r.period_start,
                period_end=r.period_end,
            )
            for r in rows
        ]

    async def update_period_spent(self, period_id: str, org_id: str, spent_cents: int) -> None:
        async with session_as_service_account(self._factory) as session:
            await session.execute(
                text(
                    """
                    UPDATE ibex_billing.budget_periods
                    SET spent_cents_cached = :spent, updated_at = now()
                    WHERE id = CAST(:period_id AS uuid)
                      AND org_id = CAST(:org_id AS uuid)
                    """
                ),
                {"period_id": period_id, "org_id": org_id, "spent": int(spent_cents)},
            )
        # session.begin() commits on successful exit — only then is spent durable.

    async def aclose(self) -> None:
        await self._engine.dispose()


def _fmt_ts(ts: datetime) -> str:
    from datetime import UTC

    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


async def run_budget_spent_rollup(
    *,
    querier: ClickHouseQuerier,
    store: PostgresSpendStore,
    invalidator: BudgetCacheInvalidator | None = None,
) -> dict[str, Any]:
    inv = invalidator or NoopBudgetCacheInvalidator()
    periods = await store.list_active_periods()
    updated = 0
    for period in periods:
        spent = querier.sum_spent(
            org_id=period.org_id,
            period_start=period.period_start,
            period_end=period.period_end,
        )
        await store.update_period_spent(period.period_id, period.org_id, spent)
        # Publish only after the UPDATE transaction has committed.
        try:
            await inv.publish_budget_update(period.org_id)
        except (OSError, RedisError) as exc:
            # Spent writes already committed; re-raise so Celery retries invalidate
            # with backoff+jitter. Period UPDATEs are idempotent for the same totals.
            logger.warning(
                "budget invalidate after rollup failed org_id=%s: %s",
                period.org_id,
                exc,
            )
            raise
        updated += 1
    return {"status": "ok", "periods_updated": updated}


@celery_app.task(
    bind=True,
    base=IbexTask,
    name=TASK_RECONCILE_USAGE_ACTUALS,
    queue="maintenance",
)
def reconcile_usage_actuals(self: IbexTask, **kwargs: Any) -> dict[str, str]:
    """Fill actual_cost_cents from provider invoices — deferred until #859.

    Tracked: https://github.com/Rick1330/ibex-harness/issues/859
    Spent rollup (TASK_BUDGET_SPENT_ROLLUP) remains the active CH→PG path.
    """
    del self, kwargs
    logger.info(
        "reconcile_usage_actuals deferred: waiting on provider invoice source (#859)"
    )
    return {
        "status": "deferred",
        "reason": "no_invoice_source",
        "tracking_issue": "https://github.com/Rick1330/ibex-harness/issues/859",
    }


@celery_app.task(
    bind=True,
    base=IbexTask,
    name=TASK_BUDGET_SPENT_ROLLUP,
    queue="maintenance",
    autoretry_for=(OSError, ClickHouseQueryError, RedisError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def budget_spent_rollup(self: IbexTask, **kwargs: Any) -> dict[str, Any]:
    """Refresh each active budget_periods.spent_cents_cached from CH period window."""
    del self, kwargs
    settings = get_settings()
    dsn = getattr(settings, "clickhouse_dsn", None)
    db_url = getattr(settings, "database_url", None)
    if not dsn or not db_url:
        logger.info("budget_spent_rollup skipped: missing clickhouse or postgres dsn")
        return {"status": "skipped", "reason": "missing_dsn"}
    querier = HttpClickHouseQuerier(dsn)
    store = SqlAlchemySpendStore(db_url)
    redis_url = getattr(settings, "redis_url", None)
    invalidator: BudgetCacheInvalidator
    if redis_url:
        invalidator = RedisBudgetCacheInvalidator(str(redis_url))
    else:
        invalidator = NoopBudgetCacheInvalidator()
    try:
        return asyncio.run(
            run_budget_spent_rollup(querier=querier, store=store, invalidator=invalidator)
        )
    finally:
        asyncio.run(store.aclose())
        aclose = getattr(invalidator, "aclose", None)
        if aclose is not None:
            asyncio.run(aclose())
