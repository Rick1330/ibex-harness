"""Auth circuit breaker unit tests."""

from __future__ import annotations

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
