"""Unit tests for the shared ledger adapter using injected session scopes."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import FrozenInstanceError
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from ibex_idempotency import (
    KIND_CONFLICT,
    KIND_IN_PROGRESS,
    KIND_OWNED,
    KIND_REPLAY,
    ClaimToken,
    LedgerConflictError,
    LedgerError,
    LedgerValidationError,
    PostgresIdempotencyLedger,
)


class _Row(dict):
    pass


class _Result:
    def __init__(self, row: _Row | None = None, rowcount: int = 0) -> None:
        self._row = row
        self.rowcount = rowcount

    def mappings(self) -> _Result:
        return self

    def first(self) -> _Row | None:
        return self._row

    def one(self) -> _Row:
        assert self._row is not None
        return self._row


class _FakeSession:
    def __init__(self, results: list[_Result]) -> None:
        self._results = list(results)
        self.executed: list[str] = []
        self.calls: list[tuple[str, dict | None]] = []

    async def execute(self, statement, params=None):  # type: ignore[no-untyped-def]
        self.executed.append(str(statement))
        self.calls.append((str(statement), params))
        return self._results.pop(0)


def _scope(session: _FakeSession):
    @asynccontextmanager
    async def _cm(_org_id: str):
        yield session

    return _cm


def _probe_scope(session: _FakeSession):
    @asynccontextmanager
    async def _cm():
        yield session

    return _cm


def _row(state: str, request_hash: str, *, status: int | None = None, version: int = 1, lease=None):
    return _Row(
        id=uuid4(),
        request_hash=request_hash,
        state=state,
        status_code=status,
        response_payload=b'{"ok":true}' if state == "finalized" else None,
        lease_expires_at=lease,
        version=version,
    )


def _ledger(session: _FakeSession, *, lease_seconds: float = 120.0) -> PostgresIdempotencyLedger:
    return PostgresIdempotencyLedger(  # type: ignore[arg-type]
        object(), lease_seconds=lease_seconds, session_scope=_scope(session)
    )


@pytest.mark.asyncio
async def test_claim_fresh_returns_owned() -> None:
    session = _FakeSession([_Result(_row("claimed", "a" * 64))])
    outcome = await _ledger(session).claim(
        org_id=uuid4(), agent_id=uuid4(), key="k", request_hash="a" * 64
    )
    assert outcome.kind == KIND_OWNED
    assert outcome.claim is not None


@pytest.mark.asyncio
async def test_claim_replays_finalized_response() -> None:
    session = _FakeSession(
        [_Result(None), _Result(_row("finalized", "a" * 64, status=201, version=2))]
    )
    outcome = await _ledger(session).claim(
        org_id=uuid4(), agent_id=uuid4(), key="k", request_hash="a" * 64
    )
    assert outcome.kind == KIND_REPLAY
    assert outcome.status == 201
    assert outcome.response == b'{"ok":true}'


@pytest.mark.asyncio
async def test_claim_reports_conflict_on_hash_mismatch() -> None:
    session = _FakeSession([_Result(_row("claimed", "b" * 64))])
    outcome = await _ledger(session).claim(
        org_id=uuid4(), agent_id=uuid4(), key="k", request_hash="a" * 64
    )
    assert outcome.kind == KIND_CONFLICT


@pytest.mark.asyncio
async def test_claim_reports_in_progress_within_lease() -> None:
    import datetime as dt

    future = dt.datetime.now(tz=dt.UTC) + timedelta(seconds=30)
    session = _FakeSession([_Result(None), _Result(_row("claimed", "a" * 64, lease=future))])
    outcome = await _ledger(session).claim(
        org_id=uuid4(), agent_id=uuid4(), key="k", request_hash="a" * 64
    )
    assert outcome.kind == KIND_IN_PROGRESS
    assert outcome.retry_after is not None and outcome.retry_after >= 1


@pytest.mark.asyncio
async def test_claim_rejects_invalid_claim() -> None:
    session = _FakeSession([])
    with pytest.raises(LedgerError):
        await _ledger(session).claim(org_id=uuid4(), agent_id=uuid4(), key="", request_hash="x")


@pytest.mark.asyncio
async def test_finalize_raises_conflict_when_not_owned() -> None:
    session = _FakeSession([_Result(None, rowcount=0)])
    claim = ClaimToken(uuid4(), uuid4(), uuid4(), "k", "a" * 64, version=1)
    with pytest.raises(LedgerConflictError):
        await _ledger(session).finalize(claim, status=201, response=b"{}")


def test_as_ledger_error_maps_foreign_key_to_validation() -> None:
    from ibex_idempotency.ledger import _as_ledger_error

    class _Orig(Exception):
        sqlstate = "23503"

    mapped = _as_ledger_error(IntegrityError("insert", {}, _Orig()))
    assert isinstance(mapped, LedgerValidationError)

    class _Other(Exception):
        sqlstate = "23505"

    assert not isinstance(
        _as_ledger_error(IntegrityError("insert", {}, _Other())), LedgerValidationError
    )


def test_claim_token_is_immutable() -> None:
    token = ClaimToken(uuid4(), uuid4(), uuid4(), "k", "a" * 64, version=1)
    with pytest.raises(FrozenInstanceError):
        token.version = 2  # type: ignore[misc]
    assert isinstance(token.claim_id, UUID)


@pytest.mark.asyncio
async def test_ping_uses_probe_scope_and_requires_all_privileges() -> None:
    session = _FakeSession(
        [
            _Result(
                _Row(
                    table_exists=True,
                    can_select=True,
                    can_insert=True,
                    can_update=True,
                    can_delete=True,
                )
            )
        ]
    )
    ledger = PostgresIdempotencyLedger(  # type: ignore[arg-type]
        object(), probe_scope=_probe_scope(session)
    )
    await ledger.ping()
    assert len(session.calls) == 1


@pytest.mark.asyncio
async def test_ping_fails_closed_when_privilege_missing() -> None:
    session = _FakeSession(
        [
            _Result(
                _Row(
                    table_exists=True,
                    can_select=True,
                    can_insert=True,
                    can_update=True,
                    can_delete=False,
                )
            )
        ]
    )
    ledger = PostgresIdempotencyLedger(  # type: ignore[arg-type]
        object(), probe_scope=_probe_scope(session)
    )
    with pytest.raises(LedgerError, match="not ready"):
        await ledger.ping()


@pytest.mark.asyncio
async def test_claim_binds_lease_as_timedelta() -> None:
    session = _FakeSession([_Result(_row("claimed", "a" * 64))])
    await _ledger(session, lease_seconds=30).claim(
        org_id=uuid4(), agent_id=uuid4(), key="k", request_hash="a" * 64
    )
    _, params = session.calls[0]
    assert params is not None and params["lease"] == timedelta(seconds=30)


@pytest.mark.asyncio
async def test_claim_reclaims_expired_lease() -> None:
    import datetime as dt

    expired = dt.datetime.now(tz=dt.UTC) - timedelta(seconds=1)
    session = _FakeSession(
        [
            _Result(None),
            _Result(_row("claimed", "a" * 64, version=2, lease=expired)),
            _Result(_Row(version=3)),
        ]
    )
    outcome = await _ledger(session).claim(
        org_id=uuid4(), agent_id=uuid4(), key="k", request_hash="a" * 64
    )
    assert outcome.kind == KIND_OWNED
    assert outcome.claim is not None and outcome.claim.version == 3


@pytest.mark.asyncio
async def test_claim_lost_reclaim_race_reports_in_progress() -> None:
    import datetime as dt

    expired = dt.datetime.now(tz=dt.UTC) - timedelta(seconds=1)
    session = _FakeSession(
        [_Result(None), _Result(_row("claimed", "a" * 64, lease=expired)), _Result(None)]
    )
    outcome = await _ledger(session).claim(
        org_id=uuid4(), agent_id=uuid4(), key="k", request_hash="a" * 64
    )
    assert outcome.kind == KIND_IN_PROGRESS
    assert outcome.retry_after == 1


@pytest.mark.asyncio
async def test_claim_missing_row_raises() -> None:
    session = _FakeSession([_Result(None), _Result(None)])
    with pytest.raises(LedgerError, match="disappeared"):
        await _ledger(session).claim(
            org_id=uuid4(), agent_id=uuid4(), key="k", request_hash="a" * 64
        )


@pytest.mark.asyncio
async def test_claim_unsupported_state_raises() -> None:
    session = _FakeSession([_Result(None), _Result(_row("failed_terminal", "a" * 64))])
    with pytest.raises(LedgerError, match="unsupported"):
        await _ledger(session).claim(
            org_id=uuid4(), agent_id=uuid4(), key="k", request_hash="a" * 64
        )


@pytest.mark.asyncio
async def test_release_raises_conflict_when_not_owned() -> None:
    session = _FakeSession([_Result(None, rowcount=0)])
    claim = ClaimToken(uuid4(), uuid4(), uuid4(), "k", "a" * 64, version=1)
    with pytest.raises(LedgerConflictError):
        await _ledger(session).release(claim)
