"""Hand-rolled AuthService circuit breaker (no new dependencies).

Closed → Open after N consecutive AuthUnavailableError → cooldown →
half-open single probe → closed on success / open on failure.
Wraps TokenValidator.validate only; ready() bypasses the breaker.
"""

from __future__ import annotations

import logging
import time
from enum import StrEnum

from prometheus_client import Counter, Gauge

from app.auth import TokenValidator, ValidateResult
from app.errors import AuthFailedError, AuthUnavailableError

logger = logging.getLogger(__name__)

AUTH_BREAKER_FAILURES = 5
AUTH_BREAKER_COOLDOWN_S = 30.0

BREAKER_TRANSITIONS = Counter(
    "ibex_mcp_auth_breaker_transitions_total",
    "Auth circuit breaker state transitions",
    ["from_state", "to_state"],
)
BREAKER_STATE = Gauge(
    "ibex_mcp_auth_breaker_state",
    "Auth circuit breaker state (0=closed, 1=open, 2=half_open)",
)


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


_STATE_GAUGE = {
    BreakerState.CLOSED: 0,
    BreakerState.OPEN: 1,
    BreakerState.HALF_OPEN: 2,
}


class BreakingTokenValidator(TokenValidator):
    """Short-circuits ValidateToken during known Auth outages."""

    def __init__(
        self,
        inner: TokenValidator,
        *,
        failure_threshold: int = AUTH_BREAKER_FAILURES,
        cooldown_seconds: float = AUTH_BREAKER_COOLDOWN_S,
    ) -> None:
        if failure_threshold < 1:
            msg = "failure_threshold must be >= 1"
            raise ValueError(msg)
        if cooldown_seconds <= 0:
            msg = "cooldown_seconds must be positive"
            raise ValueError(msg)
        self._inner = inner
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._state = BreakerState.CLOSED
        self._consecutive_failures = 0
        self._opened_at = 0.0
        BREAKER_STATE.set(_STATE_GAUGE[BreakerState.CLOSED])

    @property
    def state(self) -> BreakerState:
        return self._state

    async def validate(self, access_token: str) -> ValidateResult:
        now = time.monotonic()
        if self._state == BreakerState.OPEN:
            if now - self._opened_at < self._cooldown_seconds:
                raise AuthUnavailableError()
            self._transition(BreakerState.HALF_OPEN)

        try:
            result = await self._inner.validate(access_token)
        except AuthFailedError:
            # Invalid token is not an upstream outage — do not trip the breaker.
            self._on_success()
            raise
        except AuthUnavailableError:
            self._on_unavailable()
            raise

        self._on_success()
        return result

    async def ready(self) -> bool:
        # Bypass breaker so readiness probes do not poison or get short-circuited.
        return await self._inner.ready()

    async def aclose(self) -> None:
        await self._inner.aclose()

    def _on_success(self) -> None:
        self._consecutive_failures = 0
        if self._state != BreakerState.CLOSED:
            self._transition(BreakerState.CLOSED)

    def _on_unavailable(self) -> None:
        self._consecutive_failures += 1
        if self._state == BreakerState.HALF_OPEN:
            self._trip_open()
            return
        if (
            self._state == BreakerState.CLOSED
            and self._consecutive_failures >= self._failure_threshold
        ):
            self._trip_open()

    def _trip_open(self) -> None:
        self._opened_at = time.monotonic()
        self._transition(BreakerState.OPEN)
        logger.warning(
            "auth breaker opened consecutive_failures=%d cooldown_s=%.1f",
            self._consecutive_failures,
            self._cooldown_seconds,
        )

    def force_cooldown_elapsed_for_tests(self) -> None:
        """Test helper: make OPEN→HALF_OPEN eligible on the next validate()."""
        self._opened_at = 0.0

    def _transition(self, to: BreakerState) -> None:
        if to == self._state:
            return
        previous = self._state
        self._state = to
        BREAKER_TRANSITIONS.labels(from_state=previous.value, to_state=to.value).inc()
        BREAKER_STATE.set(_STATE_GAUGE[to])
