"""Unit tests for the erasure sweep's I/O half: claim, retire, stage, settle.

``test_lifecycle_erasure.py`` pins the decision rules that a receipt is not
trustworthy without. This module drives the machinery around them — the claim
call, the superseded-revision retirement, the state read, the per-store stages
and the settle statement — against a fake session that records the SQL and the
bound parameters it is handed. The statements themselves are exercised against
real PostgreSQL and ClickHouse in
``tests/integration/test_memory_lifecycle_erasure_postgres.py``.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import Settings
from app.tasks import lifecycle_erasure as le
from app.tasks import org_deletion_stores as _stores
from app.tasks.lifecycle_erasure import _ClaimedRow, _Erasure, _StoreOutcome, _StoreTarget

_ROW = _ClaimedRow(
    row_id="11111111-1111-1111-1111-111111111111",
    org_id="22222222-2222-2222-2222-222222222222",
    memory_id="33333333-3333-3333-3333-333333333333",
    revision=2,
    attempts=1,
    event_type="forgotten",
    deadline=None,
)

_SETTINGS = Settings(
    database_url="postgresql+asyncpg://ibex@localhost/ibex",
    lifecycle_erasure_job_timeout_seconds=900.0,
    lifecycle_erasure_store_timeout_seconds=120.0,
)

_ERASURE = _Erasure(row=_ROW, settings=_SETTINGS, factory=object())


class _Result:
    """The slice of a SQLAlchemy result the consumer reads, nothing more."""

    def __init__(self, rows: list[Any] | None = None, rowcount: int = 0) -> None:
        self._rows = list(rows or [])
        self.rowcount = rowcount

    def mappings(self) -> _Result:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)

    def first(self) -> Any:
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Replays queued results in call order and records every statement."""

    def __init__(self, *queued: Any) -> None:
        self.queued = list(queued)
        self.statements: list[tuple[str, Any]] = []

    async def execute(self, statement: Any, params: Any = None) -> _Result:
        self.statements.append((" ".join(str(statement).split()), params))
        return self.queued.pop(0) if self.queued else _Result()

    async def scalar(self, statement: Any, params: Any = None) -> Any:
        self.statements.append((" ".join(str(statement).split()), params))
        return self.queued.pop(0) if self.queued else None

    def verbs(self) -> list[str]:
        """The leading keyword of each statement, in call order."""
        return [sql.split()[0] for sql, _ in self.statements]


class _Clock:
    """A monotonic stand-in whose value the test moves explicitly."""

    def __init__(self, step: float, now: float = 1000.0) -> None:
        self.step = step
        self.now = now

    def __call__(self) -> float:
        value = self.now
        self.now += self.step
        return value


def _scope(session: _FakeSession) -> Any:
    """A stand-in for one of the tenant/purge session scopes."""

    @asynccontextmanager
    async def scope(*_args: Any, **_kwargs: Any) -> AsyncIterator[_FakeSession]:
        yield session

    return scope


def _sweep_deps(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Wire ``_run_sweep`` to a fake engine and return it."""
    engine = MagicMock()
    engine.dispose = AsyncMock()
    monkeypatch.setattr(le, "create_engine", lambda _settings: engine)
    monkeypatch.setattr(le, "create_session_factory", lambda _engine: object())
    return engine


# ---------------------------------------------------------------------------
# The sweep loop
# ---------------------------------------------------------------------------


def test_task_entrypoint_runs_one_sweep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def sweep() -> dict[str, Any]:
        return {"status": "ok", "claimed": 0}

    monkeypatch.setattr(le, "_run_sweep", sweep)
    assert le.erase_memory.run() == {"status": "ok", "claimed": 0}


@pytest.mark.asyncio
async def test_sweep_claims_settles_and_disposes_the_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _sweep_deps(monkeypatch)
    monkeypatch.setattr(le, "_claim_one", AsyncMock(return_value=_ROW))
    settle = AsyncMock(return_value="complete")
    monkeypatch.setattr(le, "_erase_row", settle)

    out = await le._run_sweep(settings=_SETTINGS)

    assert out == {
        "status": "ok",
        "claimed": 1,
        "complete": 1,
        "partial": 0,
        "failed": 0,
        "retired": 0,
    }
    settle.assert_awaited_once()
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_sweep_stops_when_nothing_is_claimable(monkeypatch: pytest.MonkeyPatch) -> None:
    _sweep_deps(monkeypatch)
    monkeypatch.setattr(le, "_claim_one", AsyncMock(return_value=None))

    out = await le._run_sweep(settings=_SETTINGS, claim_batch=3)

    assert (out["claimed"], out["complete"]) == (0, 0)


@pytest.mark.asyncio
async def test_sweep_claims_nothing_once_the_job_deadline_has_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _sweep_deps(monkeypatch)
    # Each read of the clock advances a full job budget, so the second read —
    # the loop guard — is already past the deadline the first one computed.
    monkeypatch.setattr(le, "time", SimpleNamespace(monotonic=_Clock(step=1000.0)))
    claim = AsyncMock(return_value=_ROW)
    monkeypatch.setattr(le, "_claim_one", claim)

    out = await le._run_sweep(settings=_SETTINGS)

    assert out["claimed"] == 0
    claim.assert_not_awaited()


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_one_leases_for_the_job_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    claimed = {
        "id": "id-1",
        "org_id": "org-1",
        "memory_id": "mem-1",
        "revision": 4,
        "attempts": 2,
        "event_type": "expired",
        "erasure_deadline": None,
    }
    session = _FakeSession(_Result([claimed]))
    monkeypatch.setattr(le, "session_unpinned", _scope(session))

    row = await le._claim_one(object(), _SETTINGS)

    assert row is not None
    assert (row.row_id, row.org_id, row.memory_id) == ("id-1", "org-1", "mem-1")
    assert (row.revision, row.attempts, row.event_type) == (4, 2, "expired")
    assert row.deadline is None
    assert session.statements[0][1] == {
        "claim_limit": le._CLAIM_BATCH,
        "lease_seconds": 900.0,
        "deadline_seconds": 900.0,
    }


@pytest.mark.asyncio
async def test_claim_one_returns_none_when_the_claim_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession(_Result([]))
    monkeypatch.setattr(le, "session_unpinned", _scope(session))

    assert await le._claim_one(object(), _SETTINGS) is None


# ---------------------------------------------------------------------------
# Per-row flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_erase_row_retires_a_superseded_revision_without_reading_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(le, "_retire_if_stale", AsyncMock(return_value=True))
    read = AsyncMock()
    monkeypatch.setattr(le, "_read_erasure_state", read)

    assert await le._erase_row(object(), _SETTINGS, _ROW, time.monotonic() + 10) == "retired"
    read.assert_not_awaited()


@pytest.mark.asyncio
async def test_erase_row_stages_the_provable_set_then_settles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(le, "_retire_if_stale", AsyncMock(return_value=False))
    monkeypatch.setattr(
        le,
        "_read_erasure_state",
        AsyncMock(
            return_value=(
                {"objectstore": ("s3://b/org-1/a.json",)},
                {"session_event": "verified"},
            )
        ),
    )
    staged: list[tuple[str, tuple[str, ...], dict[str, str]]] = []

    async def record(erasure, target, existing, _deadline):
        del erasure
        staged.append((target.store, target.locators, existing))
        return _StoreOutcome(store=target.store, status="verified")

    monkeypatch.setattr(le, "_erase_store", record)
    monkeypatch.setattr(le, "_settle", AsyncMock(return_value="complete"))

    assert await le._erase_row(object(), _SETTINGS, _ROW, time.monotonic() + 10) == "complete"
    assert staged == [
        ("objectstore", ("s3://b/org-1/a.json",), {"session_event": "verified"}),
        ("session_event", (), {"session_event": "verified"}),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(("rowcount", "retired"), [(1, True), (0, False)])
async def test_retire_if_stale_reports_whether_the_row_was_retired(
    monkeypatch: pytest.MonkeyPatch, rowcount: int, retired: bool
) -> None:
    session = _FakeSession(_Result(rowcount=rowcount))
    monkeypatch.setattr(le, "session_as_app_org", _scope(session))

    assert await le._retire_if_stale(object(), _ROW) is retired
    _, params = session.statements[0]
    assert params["org_id"] == _ROW.org_id
    assert params["memory_id"] == _ROW.memory_id
    assert params["revision"] == _ROW.revision


@pytest.mark.asyncio
async def test_read_erasure_state_groups_locators_and_keeps_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refs = _Result(
        [
            ("objectstore", "s3://b/org-1/a.json"),
            ("objectstore", "s3://b/org-1/b.json"),
            ("session_event", "7"),
        ]
    )
    session = _FakeSession(refs, _Result([("objectstore", "verified")]))
    monkeypatch.setattr(le, "session_as_app_org", _scope(session))

    grouped, existing = await le._read_erasure_state(object(), _ROW)

    assert grouped == {
        "objectstore": ("s3://b/org-1/a.json", "s3://b/org-1/b.json"),
        "session_event": ("7",),
    }
    assert existing == {"objectstore": "verified"}
    for _, params in session.statements:
        assert params["org_id"] == _ROW.org_id
        assert params["memory_id"] == _ROW.memory_id
        assert params["revision"] == _ROW.revision


# ---------------------------------------------------------------------------
# Store stages reached through the dispatcher
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clickhouse_stage_refuses_when_the_store_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delete = AsyncMock()
    monkeypatch.setattr(_stores, "clickhouse_configured", lambda _settings: False)
    monkeypatch.setattr(_stores, "delete_clickhouse_event", delete)

    with pytest.raises(RuntimeError, match="clickhouse is unreachable"):
        await le._stage(_StoreTarget("clickhouse", ("e1",)), _ERASURE, time.monotonic() + 5)
    delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_clickhouse_stage_deletes_every_recorded_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, str, float]] = []

    async def record(_settings, *, org_id, event_id, deadline):
        seen.append((org_id, event_id, deadline))

    monkeypatch.setattr(_stores, "clickhouse_configured", lambda _settings: True)
    monkeypatch.setattr(_stores, "delete_clickhouse_event", record)

    await le._stage(_StoreTarget("clickhouse", ("e1", "e2")), _ERASURE, 1234.5)

    assert [(org, event) for org, event, _ in seen] == [
        (_ROW.org_id, "e1"),
        (_ROW.org_id, "e2"),
    ]
    assert all(deadline == 1234.5 for *_, deadline in seen)


@pytest.mark.asyncio
async def test_session_event_stage_deletes_then_confirms_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Two DELETEs (no result read) then two counts, both reporting absence.
    session = _FakeSession(_Result(), _Result(), 0, 0)
    monkeypatch.setattr(le, "session_as_purge_org", _scope(session))

    await le._stage_session_events(("7", "8"), _ERASURE, time.monotonic() + 5)

    assert session.verbs() == ["DELETE", "DELETE", "SELECT", "SELECT"]
    assert [params["event_id"] for _, params in session.statements] == [7, 8, 7, 8]
    for _, params in session.statements:
        assert params["org_id"] == _ROW.org_id


@pytest.mark.asyncio
async def test_session_event_stage_fails_when_the_row_survives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession(_Result(), 1)
    monkeypatch.setattr(le, "session_as_purge_org", _scope(session))

    with pytest.raises(RuntimeError, match="still present"):
        await le._stage_session_events(("7",), _ERASURE, time.monotonic() + 5)


# ---------------------------------------------------------------------------
# Settle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_settle_upserts_only_fresh_receipts_then_completes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession()
    monkeypatch.setattr(le, "session_as_app_org", _scope(session))
    outcomes = [
        _StoreOutcome(store="objectstore", status="verified", fresh=False),
        _StoreOutcome(store="session_event", status="not_applicable"),
    ]

    assert await le._settle(_ERASURE, outcomes) == "complete"

    assert session.verbs() == ["INSERT", "UPDATE"]
    upsert = session.statements[0][1]
    assert upsert["store"] == "session_event"
    assert upsert["status"] == "not_applicable"
    assert upsert["idempotency_key"].endswith(":session_event")
    assert "erasure_state = 'complete'" in session.statements[1][0]
    assert session.statements[1][1] == {"id": _ROW.row_id, "org_id": _ROW.org_id}


@pytest.mark.asyncio
async def test_settle_retries_with_backoff_while_the_deadline_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession()
    monkeypatch.setattr(le, "session_as_app_org", _scope(session))
    erasure = replace(_ERASURE, row=replace(_ROW, attempts=3))
    outcomes = [_StoreOutcome(store="objectstore", status="failed", error="store_timeout")]

    assert await le._settle(erasure, outcomes) == "partial"

    sql, params = session.statements[-1]
    assert "erasure_state = 'partial'" in sql
    assert params["delay_seconds"] == 120


@pytest.mark.asyncio
async def test_settle_fails_terminally_once_the_deadline_has_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession()
    monkeypatch.setattr(le, "session_as_app_org", _scope(session))
    expired = replace(
        _ERASURE, row=replace(_ROW, deadline=datetime.now(tz=UTC) - timedelta(seconds=1))
    )

    assert await le._settle(expired, [_StoreOutcome("clickhouse", "failed")]) == "failed"

    assert "erasure_state = 'failed'" in session.statements[-1][0]
