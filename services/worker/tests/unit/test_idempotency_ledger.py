"""Unit tests for the worker PostgreSQL idempotency adapter."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app import idempotency_ledger as mod


class _Rows:
    def __init__(self, row: dict | None) -> None:
        self.row = row

    def mappings(self) -> _Rows:
        return self

    def first(self) -> dict | None:
        return self.row

    def one(self) -> dict:
        assert self.row is not None
        return self.row


class _Session:
    def __init__(self, *results: _Rows | SimpleNamespace) -> None:
        self.results = list(results)
        self.calls: list[object] = []

    async def execute(self, statement, params=None):
        self.calls.append((statement, params))
        return self.results.pop(0)


@pytest.fixture
def session_context(monkeypatch: pytest.MonkeyPatch):
    sessions: list[_Session] = []

    def install(session: _Session) -> None:
        sessions.append(session)

        @asynccontextmanager
        async def context(_factory, _org):
            yield session

        monkeypatch.setattr(mod, "session_as_service_org", context)

    return install, sessions


def _row(**overrides):
    row = {
        "id": uuid4(),
        "request_hash": "hash",
        "state": "claimed",
        "status_code": None,
        "response_payload": None,
        "lease_expires_at": None,
        "version": 1,
    }
    if "expires" in overrides:
        overrides["lease_expires_at"] = overrides.pop("expires")
    if "response" in overrides:
        overrides["response_payload"] = overrides.pop("response")
    row.update(overrides)
    if row["state"] == "finalized" and "status_code" not in overrides:
        row["status_code"] = 202
    return row


@pytest.mark.asyncio
async def test_ping_uses_service_account_session(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _Session(
        _Rows(
            {
                "table_exists": True,
                "can_select": True,
                "can_insert": True,
                "can_update": True,
                "can_delete": True,
            }
        )
    )

    @asynccontextmanager
    async def context(_factory):
        yield session

    monkeypatch.setattr(mod, "session_as_service_account", context)
    await mod.PostgresIdempotencyLedger(object()).ping()
    assert len(session.calls) == 1


@pytest.mark.asyncio
async def test_claim_rejects_invalid_key(session_context) -> None:
    ledger = mod.PostgresIdempotencyLedger(object())
    for key, request_hash in (("", "hash"), ("x" * 257, "hash"), ("k", "")):
        with pytest.raises(mod.LedgerError, match="invalid"):
            await ledger.claim(
                org_id=uuid4(), agent_id=uuid4(), key=key, request_hash=request_hash
            )


@pytest.mark.asyncio
async def test_claim_fresh_and_conflict(session_context) -> None:
    install, _ = session_context
    org_id, agent_id = uuid4(), uuid4()
    fresh_session = _Session(_Rows(_row()))
    install(fresh_session)
    ledger = mod.PostgresIdempotencyLedger(object(), lease_seconds=0)
    fresh = await ledger.claim(org_id=org_id, agent_id=agent_id, key="k", request_hash="hash")
    assert fresh.kind == "owned"
    assert fresh.claim is not None
    existing = _row(request_hash="other")
    existing_session = _Session(_Rows(None), _Rows(existing))
    install(existing_session)
    conflict = await ledger.claim(org_id=org_id, agent_id=agent_id, key="k", request_hash="hash")
    assert conflict.kind == "conflict"


@pytest.mark.asyncio
async def test_claim_binds_lease_as_timedelta(session_context) -> None:
    install, _ = session_context
    session = _Session(_Rows(_row()))
    install(session)
    ledger = mod.PostgresIdempotencyLedger(object(), lease_seconds=30)

    await ledger.claim(org_id=uuid4(), agent_id=uuid4(), key="k", request_hash="hash")

    assert session.calls[0][1]["lease"] == timedelta(seconds=30)


@pytest.mark.asyncio
async def test_claim_replays_finalized_and_reports_active_lease(session_context) -> None:
    install, _ = session_context
    org_id, agent_id = uuid4(), uuid4()
    replay_session = _Session(
        _Rows(None),
        _Rows(_row(state="finalized", response=b'{"task_id":"t"}')),
    )
    install(replay_session)
    ledger = mod.PostgresIdempotencyLedger(object())
    replay = await ledger.claim(org_id=org_id, agent_id=agent_id, key="k", request_hash="hash")
    assert replay.kind == "replay"
    assert replay.response == b'{"task_id":"t"}'
    active_session = _Session(
        _Rows(None),
        _Rows(_row(expires=datetime.now(UTC) + timedelta(seconds=10))),
    )
    install(active_session)
    active = await ledger.claim(org_id=org_id, agent_id=agent_id, key="k", request_hash="hash")
    assert active.kind == "in_progress"
    assert (active.retry_after or 0) >= 1


@pytest.mark.asyncio
async def test_claim_reclaims_expired_lease_and_handles_race(session_context) -> None:
    install, _ = session_context
    org_id, agent_id = uuid4(), uuid4()
    old = _row(expires=datetime.now(UTC) - timedelta(seconds=1), version=2)
    reclaimed = _Session(_Rows(None), _Rows(old), _Rows({"version": 3}))
    install(reclaimed)
    ledger = mod.PostgresIdempotencyLedger(object())
    outcome = await ledger.claim(org_id=org_id, agent_id=agent_id, key="k", request_hash="hash")
    assert outcome.kind == "owned"
    assert outcome.claim is not None and outcome.claim.version == 3
    raced = _Session(_Rows(None), _Rows(old), _Rows(None))
    install(raced)
    outcome = await ledger.claim(org_id=org_id, agent_id=agent_id, key="k", request_hash="hash")
    assert outcome.kind == "in_progress"
    assert outcome.retry_after == 1


@pytest.mark.asyncio
async def test_claim_rejects_missing_or_unsupported_rows(session_context) -> None:
    install, _ = session_context
    ledger = mod.PostgresIdempotencyLedger(object())
    install(_Session(_Rows(None), _Rows(None)))
    with pytest.raises(mod.LedgerError, match="disappeared"):
        await ledger.claim(org_id=uuid4(), agent_id=uuid4(), key="k", request_hash="hash")
    install(_Session(_Rows(None), _Rows(_row(state="failed_terminal"))))
    with pytest.raises(mod.LedgerError, match="unsupported"):
        await ledger.claim(org_id=uuid4(), agent_id=uuid4(), key="k", request_hash="hash")


@pytest.mark.asyncio
async def test_finalize_and_release_fence_stale_claims(session_context) -> None:
    install, _ = session_context
    ledger = mod.PostgresIdempotencyLedger(object())
    claim = mod.ClaimToken(uuid4(), uuid4(), uuid4(), "k", "hash", 1)
    install(_Session(SimpleNamespace(rowcount=1)))
    await ledger.finalize(claim, status=202, response=b"{}")
    install(_Session(SimpleNamespace(rowcount=0)))
    with pytest.raises(mod.LedgerConflictError, match="no longer owned"):
        await ledger.finalize(claim, status=202, response=b"{}")
    install(_Session(SimpleNamespace(rowcount=1)))
    await ledger.release(claim)
    install(_Session(SimpleNamespace(rowcount=0)))
    with pytest.raises(mod.LedgerConflictError, match="no longer owned"):
        await ledger.release(claim)


def test_fingerprint_is_deterministic_and_payload_sensitive() -> None:
    payload = {"org_id": "o", "agent_id": "a", "session_id": "s", "turns": []}
    assert mod.fingerprint_enqueue(payload) == mod.fingerprint_enqueue(dict(payload))
    changed = {**payload, "turns": [{"turn_index": 0, "role": "user", "content": "x"}]}
    assert mod.fingerprint_enqueue(payload) != mod.fingerprint_enqueue(changed)
