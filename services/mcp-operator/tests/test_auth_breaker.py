"""Auth circuit breaker parity with services/mcp-memory."""

from __future__ import annotations

import pytest
from mcp_gateway import GatewayPrincipal

from app.auth import StaticTokenValidator, TokenValidator
from app.auth_breaker import BreakerState, BreakingTokenValidator
from app.errors import AuthUnavailableError
from tests.fixtures import AGENT, ORG, TOKEN_A, static_validator


class _FlakyValidator(TokenValidator):
    def __init__(self) -> None:
        self.fail = False
        self.calls = 0

    async def validate(self, access_token: str) -> GatewayPrincipal:
        self.calls += 1
        if self.fail:
            raise AuthUnavailableError()
        if access_token != TOKEN_A:
            from app.errors import AuthFailedError

            raise AuthFailedError()
        return GatewayPrincipal(org_id=ORG, permissions=0, agent_id=AGENT)

    async def ready(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_breaker_opens_after_threshold_and_short_circuits() -> None:
    inner = _FlakyValidator()
    inner.fail = True
    breaker = BreakingTokenValidator(inner, failure_threshold=2, cooldown_seconds=30.0)
    for _ in range(2):
        with pytest.raises(AuthUnavailableError):
            await breaker.validate(TOKEN_A)
    assert breaker.state == BreakerState.OPEN
    calls_before = inner.calls
    with pytest.raises(AuthUnavailableError):
        await breaker.validate(TOKEN_A)
    assert inner.calls == calls_before  # short-circuited, no upstream call


@pytest.mark.asyncio
async def test_breaker_half_open_probe_closes_on_success() -> None:
    inner = _FlakyValidator()
    inner.fail = True
    breaker = BreakingTokenValidator(inner, failure_threshold=1, cooldown_seconds=30.0)
    with pytest.raises(AuthUnavailableError):
        await breaker.validate(TOKEN_A)
    assert breaker.state == BreakerState.OPEN
    inner.fail = False
    breaker.force_cooldown_elapsed_for_tests()
    await breaker.validate(TOKEN_A)
    assert breaker.state == BreakerState.CLOSED


@pytest.mark.asyncio
async def test_invalid_token_does_not_trip_breaker() -> None:
    inner = _FlakyValidator()
    breaker = BreakingTokenValidator(inner, failure_threshold=1, cooldown_seconds=30.0)
    from app.errors import AuthFailedError

    with pytest.raises(AuthFailedError):
        await breaker.validate("bad-token")
    assert breaker.state == BreakerState.CLOSED


@pytest.mark.asyncio
async def test_ready_bypasses_breaker() -> None:
    validator = static_validator()
    breaker = BreakingTokenValidator(validator, failure_threshold=1)
    assert await breaker.ready() is True


def test_breaker_rejects_bad_constructor_args() -> None:
    with pytest.raises(ValueError, match="failure_threshold"):
        BreakingTokenValidator(StaticTokenValidator({}), failure_threshold=0)
    with pytest.raises(ValueError, match="cooldown_seconds"):
        BreakingTokenValidator(StaticTokenValidator({}), cooldown_seconds=0)
