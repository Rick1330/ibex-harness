"""Unit tests for the forget path's cache-eviction discipline.

The integration suite drives these through PostgreSQL and the route; this file
pins the branches that do not need a database, so a regression in the retry or
budget decision is caught without a stack. Nothing here mocks Redis: the writer
is a test double because the subject is the request path's policy, and the actual
cache commands are tested against real Redis in ``test_hot_cache_write_unit.py``,
``test_forget_cache_guard.py`` and the worker suite.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from app.cache.memory_keys import memory_hot_key, memory_object_key
from app.routers import memory_forget_support
from app.routers.memory_forget_support import (
    CacheEvictionAttempt,
    CacheRetryPolicy,
    ForgetAddress,
    ForgetEviction,
    _cache_backoff_seconds,
    _erasure_status,
    _error_reason,
    _purge_cache,
    _record_cache_eviction,
    _retryable,
    forget_cache_scope,
    invalidate_forgotten_memory,
    read_forget_erasure,
)
from app.write.cache import CacheInvalidationError


class _Writer:
    """A cache writer that replays a scripted sequence of outcomes."""

    def __init__(self, *outcomes: object) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    async def forget_memory(self, **_kwargs: object) -> None:
        self.calls += 1
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome


class _StalledWriter:
    """A writer whose eviction never finishes inside a test budget."""

    def __init__(self, delay: float) -> None:
        self.delay = delay
        self.calls = 0

    async def forget_memory(self, **_kwargs: object) -> None:
        self.calls += 1
        await asyncio.sleep(self.delay)


def _address() -> ForgetAddress:
    return ForgetAddress(org_id=uuid4(), agent_id=uuid4(), memory_id=uuid4())


def _policy(**overrides: object) -> CacheRetryPolicy:
    base = {
        "attempts": 3,
        "base_seconds": 0.01,
        "cap_seconds": 0.02,
        "jitter_fraction": 0.0,
        "total_seconds": 1.0,
        "rng": lambda: 0.5,
        "sleep": _no_sleep,
    }
    base.update(overrides)
    return CacheRetryPolicy(**base)  # type: ignore[arg-type]


async def _no_sleep(_seconds: float) -> None:
    return None


@pytest.mark.asyncio
async def test_a_successful_eviction_is_pending_and_not_retried() -> None:
    writer = _Writer(None)
    attempt = await _purge_cache(writer, _address(), _policy())
    assert (attempt.state, attempt.error) == ("pending", None)
    assert writer.calls == 1


@pytest.mark.asyncio
async def test_a_transient_failure_is_retried_then_succeeds() -> None:
    writer = _Writer(OSError("socket closed"), None)
    attempt = await _purge_cache(writer, _address(), _policy())
    assert (attempt.state, attempt.error) == ("pending", None)
    assert writer.calls == 2


@pytest.mark.asyncio
async def test_a_non_retryable_failure_is_recorded_immediately() -> None:
    writer = _Writer(
        CacheInvalidationError(
            "memory cache eviction failed: AuthenticationError", retryable=False
        )
    )
    attempt = await _purge_cache(writer, _address(), _policy())
    assert attempt.state == "failed"
    assert "AuthenticationError" in (attempt.error or "")
    assert writer.calls == 1, "a wrong password cannot succeed on the next attempt"


@pytest.mark.asyncio
async def test_exhausted_retries_are_recorded_with_the_last_reason() -> None:
    writer = _Writer(OSError("down"), OSError("down"), OSError("down"))
    attempt = await _purge_cache(writer, _address(), _policy())
    assert attempt.state == "failed"
    assert "OSError" in (attempt.error or "")
    assert writer.calls == 3


@pytest.mark.asyncio
async def test_the_total_budget_stops_a_stalled_eviction() -> None:
    writer = _StalledWriter(delay=5.0)
    started = time.perf_counter()
    attempt = await _purge_cache(
        writer, _address(), _policy(total_seconds=0.05)
    )
    elapsed = time.perf_counter() - started
    assert elapsed < 0.75, f"the eviction outlived its budget: {elapsed:.3f}s"
    assert attempt.state == "failed"
    assert "budget" in (attempt.error or "")
    assert writer.calls == 1, "the first attempt started and was cancelled"


def test_retryability_distinguishes_outages_from_refusals() -> None:
    assert _retryable(OSError("down")) is True
    assert _retryable(TimeoutError()) is True
    assert _retryable(CacheInvalidationError("down", retryable=True)) is True
    assert _retryable(CacheInvalidationError("denied", retryable=False)) is False
    assert _retryable(ValueError("cannot change")) is False


def test_backoff_is_capped_and_jittered_both_ways() -> None:
    policy = _policy(base_seconds=0.1, cap_seconds=0.4, jitter_fraction=0.25)
    assert _cache_backoff_seconds(1, policy) == pytest.approx(0.1)
    low = _cache_backoff_seconds(
        3, _policy(
            base_seconds=0.1, cap_seconds=0.4, jitter_fraction=0.25, rng=lambda: 0.0
        )
    )
    high = _cache_backoff_seconds(
        3, _policy(
            base_seconds=0.1, cap_seconds=0.4, jitter_fraction=0.25, rng=lambda: 1.0
        )
    )
    assert low < high
    assert high <= policy.cap_seconds


def test_error_reason_is_absent_when_there_is_no_error() -> None:
    assert _error_reason(None) is None


def test_the_cache_scope_derives_both_addresses() -> None:
    address = _address()
    scope = forget_cache_scope(address)
    assert scope.object_keys == (memory_object_key(address.org_id, address.memory_id),)
    assert scope.hot_keys == (memory_hot_key(address.org_id, address.agent_id),)


@pytest.mark.asyncio
async def test_no_writer_attempts_nothing() -> None:
    """A deployment without a cache has nothing to evict, but refs were recorded."""
    eviction = ForgetEviction(address=_address(), revision=2)
    await invalidate_forgotten_memory(
        None, session_factory=object(), eviction=eviction
    )


class _Result:
    """The slice of a SQLAlchemy result the read path uses."""

    def __init__(self, first: object = None, rows: list[object] | None = None) -> None:
        self._first = first
        self._rows = list(rows or [])

    def first(self) -> object:
        return self._first

    def all(self) -> list[object]:
        return self._rows


class _Session:
    def __init__(self, *results: _Result) -> None:
        self.results = list(results)
        self.params: list[dict[str, object]] = []

    async def execute(self, _statement: object, params: dict[str, object]) -> _Result:
        self.params.append(params)
        return self.results.pop(0)


def _scope(session: _Session):
    @asynccontextmanager
    async def scope(*_args: object):
        yield session

    return scope


def test_erasure_status_prefers_a_receipt_and_reports_a_failed_cache_attempt() -> None:
    status = _erasure_status("complete", [("cache", "verified")], True)
    assert status.state == "complete"
    assert status.stores.cache == "verified", "a receipt is proof and always wins"
    assert status.stores.cache_hot == "failed", "the request attempt is work, not proof"
    assert status.stores.objectstore == "pending"


def test_unknown_values_degrade_to_no_proof_instead_of_raising() -> None:
    status = _erasure_status("nonsense", [("cache", "bogus")])
    assert (status.state, status.stores.cache) == ("pending", "pending")


def test_a_terminal_failure_stops_reporting_a_verified_receipt_as_current() -> None:
    """A failed job settles the store's current state, not its old proof."""
    status = _erasure_status("failed", [("session_event", "verified")])
    assert status.state == "failed"
    assert status.stores.session_event == "failed"
    assert status.stores.objectstore == "pending", "no receipt stays pending, not failed"


def test_a_live_job_still_reports_a_verified_receipt() -> None:
    """The downgrade is the failed job's, not a blanket rule about receipts."""
    status = _erasure_status("partial", [("session_event", "verified")])
    assert status.stores.session_event == "verified"


@pytest.mark.asyncio
async def test_read_forget_erasure_maps_the_row_and_the_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session(
        _Result(first=("partial", "failed")),
        _Result(rows=[("objectstore", "verified"), ("cache_hot", "failed")]),
    )
    monkeypatch.setattr(memory_forget_support, "session_with_org", _scope(session))
    org_id, memory_id = uuid4(), uuid4()

    status = await read_forget_erasure(
        object(), org_id=org_id, memory_id=memory_id, revision=2
    )

    assert status.state == "partial"
    assert status.stores.objectstore == "verified"
    assert status.stores.cache == "failed"
    assert all(isinstance(params["org_id"], object) for params in session.params)
    assert session.params[0]["revision"] == 2


@pytest.mark.asyncio
async def test_read_forget_erasure_degrades_when_the_row_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_args: object):
        raise RuntimeError("database down")

    monkeypatch.setattr(memory_forget_support, "session_with_org", boom)

    status = await read_forget_erasure(
        object(), org_id=uuid4(), memory_id=uuid4(), revision=2
    )

    assert status.state == "pending"
    assert status.stores.objectstore == "pending"


@pytest.mark.asyncio
async def test_record_cache_eviction_writes_both_attempt_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session(_Result())
    monkeypatch.setattr(memory_forget_support, "session_with_org", _scope(session))
    eviction = ForgetEviction(address=_address(), revision=3)

    await _record_cache_eviction(
        object(), eviction, CacheEvictionAttempt(state="failed", error="timeout")
    )

    params = session.params[0]
    assert params["state"] == "failed"
    assert params["error"] == "timeout"
    assert params["revision"] == 3
    assert params["memory_id"] == str(eviction.address.memory_id)


@pytest.mark.asyncio
async def test_a_transport_timeout_is_not_misreported_as_the_budget() -> None:
    """A writer's own timeout is recorded as what it was, not as the budget.

    ``asyncio.wait_for`` raises the builtin ``TimeoutError`` and a transport can
    raise the same class. Only elapsed time distinguishes the two, and the outbox
    reason an operator reads must not blame a budget that was not reached.
    """
    writer = _Writer(
        TimeoutError("upstream slow"),
        TimeoutError("upstream slow"),
        TimeoutError("upstream slow"),
    )
    attempt = await _purge_cache(writer, _address(), _policy())
    assert attempt.state == "failed"
    assert writer.calls == 3, "a transport timeout is retryable"
    assert "budget" not in (attempt.error or "")
    assert "TimeoutError" in (attempt.error or "")
