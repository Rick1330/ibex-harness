"""Hand-rolled AuthService circuit breaker (no new dependencies).

Closed → Open after N consecutive AuthUnavailableError → cooldown →
half-open single probe → closed on success / open on failure.
Wraps TokenValidator.validate only; ready() bypasses the breaker.

Half-open allows exactly one in-flight Auth probe; concurrent callers are
rejected with AuthUnavailableError until that probe completes.
"""

from __future__ import annotations

import logging
import threading
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
        self._probe_inflight = False
        # threading.Lock: never held across await (avoids asyncio loop/lock coupling).
        self._lock = threading.Lock()
        BREAKER_STATE.set(_STATE_GAUGE[BreakerState.CLOSED])

    @property
    def state(self) -> BreakerState:
        return self._state

    async def validate(self, access_token: str) -> ValidateResult:
        is_probe = self._reserve_or_reject()
        try:
            result = await self._inner.validate(access_token)
        except AuthFailedError:
            # Invalid token is not an upstream outage — do not trip the breaker.
            self._record_outcome(success=True)
            raise
        except AuthUnavailableError:
            self._record_outcome(success=False)
            raise
        except Exception:
            with self._lock:
                if self._state == BreakerState.HALF_OPEN:
                    self._trip_open()
            raise
        else:
            self._record_outcome(success=True)
            return result
        finally:
            if is_probe:
                self._release_probe_reservation()

    def _reserve_or_reject(self) -> bool:
        """Return True when this caller owns the half-open Auth probe."""
        with self._lock:
            now = time.monotonic()
            if self._state == BreakerState.OPEN:
                if now - self._opened_at < self._cooldown_seconds:
                    raise AuthUnavailableError()
                if self._probe_inflight:
                    raise AuthUnavailableError()
                self._probe_inflight = True
                self._transition(BreakerState.HALF_OPEN)
                return True
            if self._state == BreakerState.HALF_OPEN:
                raise AuthUnavailableError()
            return False

    def _record_outcome(self, *, success: bool) -> None:
        with self._lock:
            if success:
                self._on_success()
            else:
                self._on_unavailable()

    def _release_probe_reservation(self) -> None:
        with self._lock:
            self._probe_inflight = False

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
