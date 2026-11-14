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

from app.auth.client import ValidateResult
from app.erased_response import ERASED_MARKER_BODY, is_erased_marker
from app.exceptions import DuplicateMemoryError, StaleLifecycleError, ValidationError
from app.routers.memory_write_authz import ensure_write_agent_authorized
from app.routers.memory_write_errors import (
    http_error_for_unknown_agent,
    http_error_for_write,
    is_unknown_agent_ledger_rejection,
    is_unknown_agent_violation,
)
from app.routers.memory_write_idempotency import (
    _FINALIZE_ATTEMPTS,
    Principal,
    begin_idempotency,
    commit_idempotency,
    commit_idempotency_fail_closed,
    erased_create_prepare,
    release_idempotency,
)
from tests.unit.memory_test_support import (
    AgentFkViolationOpts,
    LedgerFkViolationOpts,
    active_idempotency_handle,
    agent_fk_violation_integrity_error,
    ledger_validation_error,
)


def _owned() -> ClaimOutcome:
    claim = ClaimToken(uuid4(), uuid4(), uuid4(), "k", "f" * 64, version=1)
    return ClaimOutcome(kind=KIND_OWNED, claim=claim)


async def _begin(ledger, **overrides):
    kwargs = {
        "ledger": ledger,
        "principal": Principal(org_id=uuid4(), agent_id=uuid4()),
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
async def test_begin_idempotency_replay_of_an_erased_create_is_409() -> None:
    """A forgotten memory's key must not replay a 201 for content that is gone."""
    ledger = AsyncMock()
    ledger.claim = AsyncMock(
        return_value=ClaimOutcome(kind=KIND_REPLAY, status=201, response=ERASED_MARKER_BODY)
    )
    with pytest.raises(HTTPException) as exc:
        await _begin(ledger)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "IDEMPOTENCY_KEY_ERASED"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (None, False),
        (b"", False),
        (b"not-json", False),
        (b'{"erased": false}', False),
        (b'{"erased": true, "extra": 1}', False),
        (ERASED_MARKER_BODY, True),
    ],
    ids=["none", "empty", "invalid", "false", "extra-keys", "marker"],
)
def test_is_erased_marker_only_accepts_the_marker(payload, expected: bool) -> None:
    assert is_erased_marker(payload) is expected


class _FakeExecuteResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


class _FakePrepareSession:
    def __init__(self, value: object) -> None:
        self._value = value

    async def execute(self, statement: object, params: object = None) -> _FakeExecuteResult:
        del statement, params
        return _FakeExecuteResult(self._value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tombstoned", "expected"),
    [(True, ERASED_MARKER_BODY), (None, ERASED_MARKER_BODY), (False, b'{"data":{}}')],
    ids=["tombstoned", "missing", "live"],
)
async def test_erased_create_prepare_returns_the_marker_only_for_a_dead_row(
    tombstoned: object, expected: bytes
) -> None:
    prepare = erased_create_prepare(
        memory_id=uuid4(), org_id=uuid4(), body=b'{"data":{}}'
    )
    stored = await prepare(_FakePrepareSession(tombstoned))
    assert stored == expected


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
async def test_begin_idempotency_unknown_agent_is_404() -> None:
    """A keyed write for an unknown agent must match the unkeyed 404."""
    ledger = AsyncMock()
    ledger.claim = AsyncMock(side_effect=ledger_validation_error())
    with pytest.raises(HTTPException) as exc:
        await _begin(ledger)
    assert exc.value.status_code == 404
    assert exc.value.detail == {"code": "NOT_FOUND", "message": "Agent not found"}


@pytest.mark.asyncio
async def test_begin_idempotency_unknown_org_keeps_its_400() -> None:
    """The organization case is unchanged: only the agent case has a 404 twin."""
    ledger = AsyncMock()
    ledger.claim = AsyncMock(
        side_effect=ledger_validation_error(
            LedgerFkViolationOpts(constraint_name="idempotency_ledger_organization_id_fkey")
        )
    )
    with pytest.raises(HTTPException) as exc:
        await _begin(ledger)
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "VALIDATION_ERROR"


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
    monkeypatch.setattr("app.routers.memory_write_idempotency._FINALIZE_BACKOFF_SECONDS", 0.0)
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
    monkeypatch.setattr("app.routers.memory_write_idempotency._FINALIZE_BACKOFF_SECONDS", 0.0)
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
    from app.routers.memory_write_idempotency import parse_idempotency_key

    with pytest.raises(HTTPException) as exc:
        parse_idempotency_key("k" * 300)
    assert exc.value.status_code == 400


def test_ensure_write_agent_authorized_allows_org_scoped_token() -> None:
    agent_id = uuid4()
    token = ValidateResult(org_id=uuid4(), permissions=0, agent_id=None)
    ensure_write_agent_authorized(token, agent_id)


def test_ensure_write_agent_authorized_allows_matching_agent() -> None:
    agent_id = uuid4()
    token = ValidateResult(org_id=uuid4(), permissions=0, agent_id=agent_id)
    ensure_write_agent_authorized(token, agent_id)


def test_ensure_write_agent_authorized_rejects_mismatch() -> None:
    token = ValidateResult(org_id=uuid4(), permissions=0, agent_id=uuid4())
    with pytest.raises(HTTPException) as exc:
        ensure_write_agent_authorized(token, uuid4())
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "AGENT_NOT_AUTHORIZED"


def test_is_unknown_agent_violation_matches_agent_fk() -> None:
    exc = agent_fk_violation_integrity_error()
    assert is_unknown_agent_violation(exc) is True


def test_is_unknown_agent_violation_falls_back_to_the_message() -> None:
    # Some drivers omit constraint_name; the message still names the constraint.
    exc = agent_fk_violation_integrity_error(
        AgentFkViolationOpts(constraint_name="", pgcode="23503", sqlstate=None)
    )
    assert is_unknown_agent_violation(exc) is True


def test_is_unknown_agent_violation_ignores_other_fk() -> None:
    exc = agent_fk_violation_integrity_error(
        AgentFkViolationOpts(constraint_name="memories_session_org_fk")
    )
    assert is_unknown_agent_violation(exc) is False


def test_is_unknown_agent_violation_ignores_wrong_sqlstate() -> None:
    exc = agent_fk_violation_integrity_error(AgentFkViolationOpts(sqlstate="23505"))
    assert is_unknown_agent_violation(exc) is False


def test_is_unknown_agent_violation_ignores_non_integrity_error() -> None:
    assert is_unknown_agent_violation(RuntimeError("boom")) is False


def test_is_unknown_agent_violation_without_an_orig() -> None:
    from sqlalchemy.exc import IntegrityError

    exc = IntegrityError("insert", {}, Exception("fk"))
    exc.orig = None
    assert is_unknown_agent_violation(exc) is False


def test_is_unknown_agent_violation_unrelated_message_is_false() -> None:
    exc = agent_fk_violation_integrity_error(
        AgentFkViolationOpts(constraint_name="", message="some foreign key violation")
    )
    assert is_unknown_agent_violation(exc) is False


def test_http_error_for_unknown_agent_is_404() -> None:
    exc = http_error_for_unknown_agent()
    assert exc.status_code == 404
    assert exc.detail == {"code": "NOT_FOUND", "message": "Agent not found"}


def test_is_unknown_agent_ledger_rejection_matches_the_ledger_agent_fk() -> None:
    assert is_unknown_agent_ledger_rejection(ledger_validation_error()) is True


def test_is_unknown_agent_ledger_rejection_ignores_the_ledger_org_fk() -> None:
    exc = ledger_validation_error(
        LedgerFkViolationOpts(constraint_name="idempotency_ledger_organization_id_fkey")
    )
    assert is_unknown_agent_ledger_rejection(exc) is False


def test_is_unknown_agent_ledger_rejection_falls_back_to_the_message() -> None:
    # Some drivers omit constraint_name; the message still names the constraint.
    exc = ledger_validation_error(LedgerFkViolationOpts(constraint_name=""))
    assert is_unknown_agent_ledger_rejection(exc) is True


def test_is_unknown_agent_ledger_rejection_requires_a_cause() -> None:
    assert is_unknown_agent_ledger_rejection(LedgerValidationError("no cause")) is False


def test_is_unknown_agent_ledger_rejection_ignores_a_non_fk_cause() -> None:
    exc = LedgerValidationError("rejected")
    exc.__cause__ = RuntimeError("boom")
    assert is_unknown_agent_ledger_rejection(exc) is False


def test_is_unknown_agent_ledger_rejection_ignores_a_wrong_sqlstate() -> None:
    exc = ledger_validation_error(LedgerFkViolationOpts(sqlstate="23505"))
    assert is_unknown_agent_ledger_rejection(exc) is False
