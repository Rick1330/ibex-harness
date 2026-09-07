"""Auth circuit breaker unit tests."""

from __future__ import annotations

import asyncio
import threading

import pytest

from app.auth import StaticTokenValidator, ValidateResult
from app.auth_breaker import (
    AUTH_BREAKER_COOLDOWN_S,
    AUTH_BREAKER_FAILURES,
    BreakerState,
    BreakingTokenValidator,
)
from app.errors import AuthFailedError, AuthUnavailableError
from tests.memory_fixtures import AGENT, ORG


@pytest.mark.asyncio
async def test_breaker_opens_after_n_unavailable() -> None:
    inner = StaticTokenValidator({}, available=False)
    breaker = BreakingTokenValidator(
        inner, failure_threshold=3, cooldown_seconds=60.0
    )
    for _ in range(3):
        with pytest.raises(AuthUnavailableError):
            await breaker.validate("x")
    assert breaker.state == BreakerState.OPEN
    # Short-circuit: no further inner call needed
    with pytest.raises(AuthUnavailableError):
        await breaker.validate("x")


@pytest.mark.asyncio
async def test_breaker_auth_failed_does_not_trip() -> None:
    inner = StaticTokenValidator({})
    breaker = BreakingTokenValidator(
        inner, failure_threshold=2, cooldown_seconds=60.0
    )
    for _ in range(5):
        with pytest.raises(AuthFailedError):
            await breaker.validate("bad")
    assert breaker.state == BreakerState.CLOSED


@pytest.mark.asyncio
async def test_breaker_half_open_success_closes() -> None:
    token = "good"
    inner = StaticTokenValidator(
        {token: ValidateResult(org_id=ORG, permissions=1, agent_id=AGENT)},
        available=False,
    )
    breaker = BreakingTokenValidator(
        inner, failure_threshold=2, cooldown_seconds=0.01
    )
    for _ in range(2):
        with pytest.raises(AuthUnavailableError):
            await breaker.validate(token)
    assert breaker.state == BreakerState.OPEN
    breaker.force_cooldown_elapsed_for_tests()
    inner.set_available(True)
    result = await breaker.validate(token)
    assert result.org_id == ORG
    assert breaker.state == BreakerState.CLOSED


@pytest.mark.asyncio
async def test_breaker_ready_bypasses_open_state() -> None:
    inner = StaticTokenValidator({}, available=True)
    breaker = BreakingTokenValidator(
        inner, failure_threshold=1, cooldown_seconds=60.0
    )
    inner.set_available(False)
    with pytest.raises(AuthUnavailableError):
        await breaker.validate("x")
    assert breaker.state == BreakerState.OPEN
    inner.set_available(True)
    assert await breaker.ready() is True
    assert breaker.state == BreakerState.OPEN  # ready did not mutate


def test_breaker_defaults_match_go_package() -> None:
    assert AUTH_BREAKER_FAILURES == 5
    assert AUTH_BREAKER_COOLDOWN_S == 30.0


def test_breaker_rejects_invalid_ctor_args() -> None:
    inner = StaticTokenValidator({})
    with pytest.raises(ValueError, match="failure_threshold"):
        BreakingTokenValidator(inner, failure_threshold=0)
    with pytest.raises(ValueError, match="cooldown"):
        BreakingTokenValidator(inner, cooldown_seconds=0.0)


@pytest.mark.asyncio
async def test_breaker_half_open_failure_reopens() -> None:
    inner = StaticTokenValidator({}, available=False)
    breaker = BreakingTokenValidator(
        inner, failure_threshold=2, cooldown_seconds=60.0
    )
    for _ in range(2):
        with pytest.raises(AuthUnavailableError):
            await breaker.validate("x")
    assert breaker.state == BreakerState.OPEN
    breaker.force_cooldown_elapsed_for_tests()
    with pytest.raises(AuthUnavailableError):
        await breaker.validate("x")
    assert breaker.state == BreakerState.OPEN


def test_breaker_transition_noop_when_unchanged() -> None:
    breaker = BreakingTokenValidator(
        StaticTokenValidator({}), failure_threshold=2, cooldown_seconds=1.0
    )
    breaker._transition(BreakerState.CLOSED)
    assert breaker.state == BreakerState.CLOSED


@pytest.mark.asyncio
async def test_breaker_aclose_delegates() -> None:
    inner = StaticTokenValidator({})
    breaker = BreakingTokenValidator(inner, failure_threshold=1, cooldown_seconds=1.0)
    await breaker.aclose()


@pytest.mark.asyncio
async def test_breaker_half_open_single_probe_under_concurrency() -> None:
    """Only one caller may reserve the half-open Auth probe."""
    inner = StaticTokenValidator(
        {"tok": ValidateResult(org_id=ORG, permissions=1, agent_id=AGENT)},
        available=True,
    )
    breaker = BreakingTokenValidator(
        inner, failure_threshold=2, cooldown_seconds=60.0
    )
    # Simulate OPEN past cooldown, then contend for the single probe reservation.
    breaker._state = BreakerState.OPEN
    breaker._opened_at = 0.0
    breaker._probe_inflight = False

    reserved: list[bool | str] = []
    barrier = threading.Barrier(16)

    def worker() -> None:
        barrier.wait()
        try:
            reserved.append(breaker._reserve_or_reject())
        except AuthUnavailableError:
            reserved.append("reject")

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=2.0)
        assert not t.is_alive()

    assert reserved.count(True) == 1
    assert reserved.count("reject") == 15
    assert breaker.state == BreakerState.HALF_OPEN
    assert breaker._probe_inflight is True

    # Concurrent validate while probe is reserved must not call Auth.
    calls_before = 0

    async def counting_validate(access_token: str) -> ValidateResult:
        nonlocal calls_before
        calls_before += 1
        return await StaticTokenValidator.validate(inner, access_token)

    inner.validate = counting_validate  # type: ignore[method-assign]
    outcomes = await asyncio.gather(
        *[breaker.validate("tok") for _ in range(8)],
        return_exceptions=True,
    )
    assert all(isinstance(o, AuthUnavailableError) for o in outcomes)
    assert calls_before == 0

    breaker._release_probe_reservation()
    breaker._record_outcome(success=True)
    assert breaker.state == BreakerState.CLOSED
