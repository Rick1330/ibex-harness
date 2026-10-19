"""Unit tests for memory write HTTP support helpers (ledger-backed idempotency)."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from ibex_idempotency import (
    KIND_CONFLICT,
    KIND_IN_PROGRESS,
    KIND_OWNED,
    KIND_REPLAY,
    ClaimOutcome,
    ClaimToken,
    LedgerConflictError,
    LedgerError,
    LedgerValidationError,
)

from app.exceptions import DuplicateMemoryError, StaleLifecycleError, ValidationError
from app.routers.memory_write_support import (
    _FINALIZE_ATTEMPTS,
    begin_idempotency,
    commit_idempotency,
    commit_idempotency_fail_closed,
    http_error_for_write,
    release_idempotency,
)
from tests.unit.memory_test_support import active_idempotency_handle


def _owned() -> ClaimOutcome:
    claim = ClaimToken(uuid4(), uuid4(), uuid4(), "k", "f" * 64, version=1)
    return ClaimOutcome(kind=KIND_OWNED, claim=claim)


async def _begin(ledger, **overrides):
    kwargs = {
        "ledger": ledger,
        "org_id": uuid4(),
        "agent_id": uuid4(),
        "idempotency_key": "k",
        "request_hash": "f" * 64,
    }
    kwargs.update(overrides)
    return await begin_idempotency(**kwargs)


@pytest.mark.asyncio
async def test_begin_idempotency_skips_without_key() -> None:
    handle = await _begin(AsyncMock(), idempotency_key=None)
    assert handle.claim is None


@pytest.mark.asyncio
async def test_begin_idempotency_treats_whitespace_as_absent() -> None:
    handle = await _begin(AsyncMock(), idempotency_key="   ")
    assert handle.claim is None


@pytest.mark.asyncio
async def test_begin_idempotency_replay_returns_json() -> None:
    ledger = AsyncMock()
    ledger.claim = AsyncMock(
        return_value=ClaimOutcome(kind=KIND_REPLAY, status=201, response=b'{"ok":true}')
    )
    result = await _begin(ledger)
    assert isinstance(result, JSONResponse)
    assert result.status_code == 201
    assert result.headers["x-idempotency-replayed"] == "true"


@pytest.mark.asyncio
async def test_begin_idempotency_owned_returns_active_handle() -> None:
    ledger = AsyncMock()
    ledger.claim = AsyncMock(return_value=_owned())
    handle = await _begin(ledger)
    assert handle.active
    assert handle.claim is not None


@pytest.mark.asyncio
async def test_begin_idempotency_conflict_is_409() -> None:
    ledger = AsyncMock()
    ledger.claim = AsyncMock(return_value=ClaimOutcome(kind=KIND_CONFLICT))
    with pytest.raises(HTTPException) as exc:
        await _begin(ledger)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.asyncio
async def test_begin_idempotency_in_progress_is_409() -> None:
    ledger = AsyncMock()
    ledger.claim = AsyncMock(return_value=ClaimOutcome(kind=KIND_IN_PROGRESS, retry_after=5))
    with pytest.raises(HTTPException) as exc:
        await _begin(ledger)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "IDEMPOTENCY_IN_PROGRESS"
    assert exc.value.headers == {"Retry-After": "5"}


@pytest.mark.asyncio
async def test_begin_idempotency_without_ledger_fails_closed() -> None:
    with pytest.raises(HTTPException) as exc:
        await _begin(None)
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "IDEMPOTENCY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_begin_idempotency_validation_error_is_400() -> None:
    ledger = AsyncMock()
    ledger.claim = AsyncMock(side_effect=LedgerValidationError("bad agent"))
    with pytest.raises(HTTPException) as exc:
        await _begin(ledger)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_begin_idempotency_ledger_error_fails_closed() -> None:
    ledger = AsyncMock()
    ledger.claim = AsyncMock(side_effect=LedgerError("down"))
    with pytest.raises(HTTPException) as exc:
        await _begin(ledger)
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "IDEMPOTENCY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_release_and_commit_when_active() -> None:
    ledger = AsyncMock()
    handle = active_idempotency_handle(ledger=ledger)
    await release_idempotency(handle)
    ledger.release.assert_awaited_once()
    await commit_idempotency(handle, status=201, body=b"{}")
    ledger.finalize.assert_awaited_once()


@pytest.mark.asyncio
async def test_release_idempotency_swallows_ledger_error() -> None:
    ledger = AsyncMock()
    ledger.release = AsyncMock(side_effect=LedgerError("down"))
    handle = active_idempotency_handle(ledger=ledger)
    await release_idempotency(handle)
    ledger.release.assert_awaited_once()


@pytest.mark.asyncio
async def test_commit_fail_closed_retries_then_returns_503(monkeypatch) -> None:
    monkeypatch.setattr("app.routers.memory_write_support._FINALIZE_BACKOFF_SECONDS", 0.0)
    ledger = AsyncMock()
    ledger.finalize = AsyncMock(side_effect=LedgerError("down"))
    handle = active_idempotency_handle(ledger=ledger)
    with pytest.raises(HTTPException) as exc:
        await commit_idempotency_fail_closed(handle, status=201, body=b"{}")
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "IDEMPOTENCY_UNAVAILABLE"
    assert ledger.finalize.await_count == _FINALIZE_ATTEMPTS


@pytest.mark.asyncio
async def test_commit_fail_closed_recovers_on_transient_retry(monkeypatch) -> None:
    monkeypatch.setattr("app.routers.memory_write_support._FINALIZE_BACKOFF_SECONDS", 0.0)
    ledger = AsyncMock()
    ledger.finalize = AsyncMock(side_effect=[LedgerError("blip"), None])
    handle = active_idempotency_handle(ledger=ledger)
    await commit_idempotency_fail_closed(handle, status=201, body=b"{}")
    assert ledger.finalize.await_count == 2


@pytest.mark.asyncio
async def test_commit_fail_closed_does_not_retry_lost_claim() -> None:
    ledger = AsyncMock()
    ledger.finalize = AsyncMock(side_effect=LedgerConflictError("claim lost"))
    handle = active_idempotency_handle(ledger=ledger)
    with pytest.raises(HTTPException) as exc:
        await commit_idempotency_fail_closed(handle, status=201, body=b"{}")
    assert exc.value.status_code == 503
    assert ledger.finalize.await_count == 1


def test_http_error_for_write_maps_duplicate() -> None:
    exc = http_error_for_write(DuplicateMemoryError(uuid4()))
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 409


def test_http_error_for_write_maps_validation() -> None:
    exc = http_error_for_write(ValidationError("bad", field="content"))
    assert exc.status_code == 400
    assert exc.detail["code"] == "VALIDATION_ERROR"


def test_http_error_for_write_maps_stale_lifecycle() -> None:
    exc = http_error_for_write(StaleLifecycleError("stale"))
    assert exc.status_code == 409
    assert exc.detail["code"] == "STALE_LIFECYCLE_REVISION"


def test_parse_idempotency_key_rejects_too_long() -> None:
    from app.routers.memory_write_support import parse_idempotency_key

    with pytest.raises(HTTPException) as exc:
        parse_idempotency_key("k" * 300)
    assert exc.value.status_code == 400
