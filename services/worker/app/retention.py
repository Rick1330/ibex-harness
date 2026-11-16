"""P1-21 / P2-12 / P2-15: bounded retention for stores that outlive their use.

Three windows, one sweep, because they share a schedule and a failure mode:

* ``failed_tasks`` — the dead-letter row keeps forensic value, its payload does
  not. Payload columns are overwritten at the scrub window; the row is deleted
  at the retention window. Scrubbing is not redundant with caller-side
  redaction: the caller redacts what it knows about, while ``args``/``kwargs``
  are whatever the task was handed, and ``traceback`` embeds reprs of live
  objects. This is the only place that sees the row after the fact.
* ``idempotency_ledger`` — a replay record only needs to outlive the retry
  window it protects. Only ``finalized`` rows are removed; a live claim is
  in-flight work, and deleting it would let the caller's retry run twice.
* ``usage_facts`` (ClickHouse) — financial facts, kept by month. The sweep drops
  whole partitions rather than deleting rows: a partition is the physical unit,
  a row-level delete rewrites parts, and a partition covers every tenant, so
  this is a recorded exception to "every ClickHouse statement names org_id".

The Postgres side calls one SECURITY DEFINER function per window (migration
000076). ``ibex_worker`` holds no grant on either table and is NOINHERIT, so the
function owner is what makes the sweep cross-tenant; the sweep itself issues no
row-level DML and names no org. That is the second recorded exception to
"every Postgres statement filters ``org_id`` explicitly" (AGENTS.md §4.1),
alongside the ClickHouse partition drop above: retention is a store-wide policy,
``failed_tasks.org_id`` is nullable, and no tenant identity holds EXECUTE on the
functions. It is confined to those definer bodies; nothing else may take it.

The two backends are gated independently. A worker may run with ClickHouse and
no PostgreSQL (or the reverse), and a missing DSN for one must not postpone the
window the other still enforces.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Protocol

import httpx
from sqlalchemy import text

from app.config import Settings, get_settings
from app.db import create_engine, create_session_factory, session_unpinned
from app.extraction.clickhouse_traces import _http_endpoint, shared_clickhouse_client

logger = logging.getLogger(__name__)

# ClickHouse partition ids for `toYYYYMM(event_date)` are exactly six digits.
# Anything else is refused before it reaches DDL.
_PARTITION_PATTERN = re.compile(r"^\d{6}$")
_MONTHS_PER_YEAR = 12
_CLICKHOUSE_TIMEOUT_SECONDS = 30.0

_SCRUB_SQL = "SELECT ibex_core.retention_scrub_failed_tasks(:before)"
_DELETE_TASKS_SQL = "SELECT ibex_core.retention_delete_failed_tasks(:before)"
_DELETE_LEDGER_SQL = "SELECT ibex_core.retention_delete_finalized_idempotency(:before)"

_LIST_PARTITIONS_SQL = (
    "SELECT DISTINCT partition_id AS month FROM system.parts "
    "WHERE database = 'ibex' AND table = 'usage_facts' AND active "
    "FORMAT JSONEachRow"
)


class RetentionStore(Protocol):
    """The three Postgres windows, each taking its own cutoff."""

    async def scrub_failed_tasks(self, before: datetime) -> int: ...

    async def delete_failed_tasks(self, before: datetime) -> int: ...

    async def delete_finalized_ledger(self, before: datetime) -> int: ...


class UsageFactsPartitions(Protocol):
    """Month partitions of ``ibex.usage_facts``."""

    def list_months(self) -> list[str]: ...

    def drop_month(self, month: str) -> None: ...


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """The four windows, as durations so the sweep takes one clock reading."""

    scrub_after: timedelta
    delete_after: timedelta
    ledger_after: timedelta
    keep_months: int

    @classmethod
    def from_settings(cls, settings: Settings) -> RetentionPolicy:
        return cls(
            scrub_after=timedelta(days=settings.failed_tasks_scrub_days),
            delete_after=timedelta(days=settings.failed_tasks_retention_days),
            ledger_after=timedelta(hours=settings.idempotency_ledger_retention_hours),
            keep_months=settings.usage_facts_retention_months,
        )


@dataclass(frozen=True, slots=True)
class RetentionReport:
    scrubbed: int
    deleted_tasks: int
    deleted_ledger: int
    dropped_months: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "scrubbed": self.scrubbed,
            "deleted_tasks": self.deleted_tasks,
            "deleted_ledger": self.deleted_ledger,
            "dropped_months": list(self.dropped_months),
        }


class NoopUsageFactsPartitions:
    """Stand-in when no ClickHouse DSN is configured; reports nothing to drop."""

    def list_months(self) -> list[str]:
        return []

    def drop_month(self, month: str) -> None:
        raise AssertionError(f"drop_month called with no partition source: {month}")


class SqlAlchemyRetentionStore:
    """Runs the three windows through their SECURITY DEFINER functions."""

    def __init__(self, database_url: str) -> None:
        settings = SimpleNamespace(database_url=database_url) if database_url else get_settings()
        self._engine = create_engine(settings)  # type: ignore[arg-type]
        self._factory = create_session_factory(self._engine)

    async def scrub_failed_tasks(self, before: datetime) -> int:
        return await self._count(_SCRUB_SQL, before)

    async def delete_failed_tasks(self, before: datetime) -> int:
        return await self._count(_DELETE_TASKS_SQL, before)

    async def delete_finalized_ledger(self, before: datetime) -> int:
        return await self._count(_DELETE_LEDGER_SQL, before)

    async def _count(self, statement: str, before: datetime) -> int:
        # Unpinned on purpose: the cross-tenant reach is the function owner's,
        # and `ibex_worker` has no grant to do this as itself.
        async with session_unpinned(self._factory) as session:
            result = await session.execute(text(statement), {"before": before})
            return int(result.scalar_one())

    async def aclose(self) -> None:
        await self._engine.dispose()


class ClickHouseUsageFactsPartitions:
    """Lists and drops ``ibex.usage_facts`` month partitions over HTTP."""

    def __init__(self, dsn: str, client: httpx.Client | None = None) -> None:
        self._dsn = dsn
        self._client = client or shared_clickhouse_client()

    def list_months(self) -> list[str]:
        months: list[str] = []
        for raw in self._query(_LIST_PARTITIONS_SQL).splitlines():
            line = raw.strip()
            if not line:
                continue
            month = str(json.loads(line).get("month"))
            if not _PARTITION_PATTERN.match(month):
                raise ValueError(f"unexpected usage_facts partition id: {month!r}")
            months.append(month)
        return sorted(months)

    def drop_month(self, month: str) -> None:
        # The partition id is an identifier in DDL, so ClickHouse cannot bind it
        # as a parameter; the six-digit check is what keeps it from being code.
        if not _PARTITION_PATTERN.match(month):
            raise ValueError(f"unexpected usage_facts partition id: {month!r}")
        self._query(
            f"ALTER TABLE ibex.usage_facts DROP PARTITION ID '{month}'"  # nosec B608
        )

    def _query(self, sql: str) -> str:
        url, auth = _http_endpoint(self._dsn)
        try:
            resp = self._client.post(
                url,
                params={"query": sql},
                auth=auth,
                timeout=_CLICKHOUSE_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise OSError(f"clickhouse retention transport failed: {exc}") from exc
        if resp.status_code >= 400:
            raise OSError(f"clickhouse retention query failed: {resp.status_code}")
        return resp.text


def month_cutoff(now: datetime, keep_months: int) -> str:
    """Return the oldest month still inside the window, as ``YYYYMM``.

    A partition is dropped when its id sorts before this value, so the boundary
    month is kept whole: the window is counted in calendar months, not in days,
    because that is how the table is partitioned.
    """
    if keep_months < 0:
        raise ValueError("keep_months must be non-negative")
    index = now.year * _MONTHS_PER_YEAR + (now.month - 1) - keep_months
    year, month = divmod(index, _MONTHS_PER_YEAR)
    if year < 1:
        raise ValueError("retention window reaches before year 1")
    return f"{year:04d}{month + 1:02d}"


def partitions_to_drop(months: Iterable[str], cutoff: str) -> list[str]:
    """Return the partition ids older than ``cutoff``, refusing unknown shapes."""
    selected: list[str] = []
    for month in months:
        if not _PARTITION_PATTERN.match(month):
            raise ValueError(f"unexpected usage_facts partition id: {month!r}")
        if month < cutoff:
            selected.append(month)
    return sorted(selected)


async def _postgres_windows(
    store: RetentionStore, at: datetime, policy: RetentionPolicy
) -> tuple[int, int, int]:
    # Scrub first: a row past both windows is deleted anyway, but content must
    # be gone even if the delete fails.
    scrubbed = await store.scrub_failed_tasks(at - policy.scrub_after)
    deleted_tasks = await store.delete_failed_tasks(at - policy.delete_after)
    deleted_ledger = await store.delete_finalized_ledger(at - policy.ledger_after)
    return scrubbed, deleted_tasks, deleted_ledger


async def run_retention_sweep(
    *,
    store: RetentionStore | None,
    partitions: UsageFactsPartitions,
    policy: RetentionPolicy,
    now: datetime | None = None,
) -> RetentionReport:
    """Apply every configured window once. Safe to repeat: each step matches only unpurged rows.

    ``store`` is ``None`` when no PostgreSQL DSN is configured. The ClickHouse
    window does not depend on it, so an absent database must not postpone a
    partition drop; the three Postgres counts are then zero and the caller
    reports that backend as skipped rather than as a clean run.
    """
    at = now or datetime.now(UTC)
    if store is None:
        scrubbed = deleted_tasks = deleted_ledger = 0
    else:
        scrubbed, deleted_tasks, deleted_ledger = await _postgres_windows(store, at, policy)
    dropped = tuple(
        partitions_to_drop(partitions.list_months(), month_cutoff(at, policy.keep_months))
    )
    for month in dropped:
        partitions.drop_month(month)
    return RetentionReport(
        scrubbed=scrubbed,
        deleted_tasks=deleted_tasks,
        deleted_ledger=deleted_ledger,
        dropped_months=dropped,
    )
