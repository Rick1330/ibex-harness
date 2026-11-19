"""Unit tests for the erasure consumer's pure decision rules.

``app.tasks.lifecycle_erasure.decisions`` turns values into verdicts, so these
tests need no database, Redis, or clock: what state a set of store outcomes
earns, which receipt statuses count as satisfied, when a row's deadline has
passed, what a retry delay is, how a receipt is keyed, and how a
``session_events`` locator is parsed. The I/O that feeds these rules is covered
by ``test_lifecycle_erasure_store_targets.py``, ``..._staging.py``,
``..._cache.py``, and ``..._sweep.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.tasks import lifecycle_erasure as le
from app.tasks.lifecycle_erasure import SATISFIED_RECEIPT_STATUSES, _StoreOutcome
from tests.unit.lifecycle_erasure_fakes import claimed_row, erasure


def _outcome(store: str, status: str) -> _StoreOutcome:
    return _StoreOutcome(store=store, status=status)


def _three_stores(clickhouse: str) -> list[_StoreOutcome]:
    """One outcome per store the consumer stages, with ClickHouse varied."""
    return [
        _outcome("objectstore", "verified"),
        _outcome("clickhouse", clickhouse),
        _outcome("session_event", "verified"),
    ]


# ---------------------------------------------------------------------------
# Job state
# ---------------------------------------------------------------------------


def test_state_is_complete_when_every_store_is_satisfied() -> None:
    assert le._erasure_state(_three_stores("not_applicable")) == "complete"


@pytest.mark.parametrize("status", ["failed", "pending"])
def test_state_is_partial_when_any_store_is_unproven(status: str) -> None:
    assert le._erasure_state(_three_stores(status)) == "partial"


def test_not_applicable_is_satisfied_but_not_verified() -> None:
    """The two statuses are distinct facts and must stay distinct."""
    assert "not_applicable" in SATISFIED_RECEIPT_STATUSES
    assert "verified" in SATISFIED_RECEIPT_STATUSES
    assert "failed" not in SATISFIED_RECEIPT_STATUSES
    assert "pending" not in SATISFIED_RECEIPT_STATUSES


def test_deadline_passed_only_after_the_recorded_deadline() -> None:
    future = datetime.now(tz=UTC) + timedelta(seconds=60)
    past = datetime.now(tz=UTC) - timedelta(seconds=1)
    assert le._deadline_passed(claimed_row(deadline=future)) is False
    assert le._deadline_passed(claimed_row(deadline=past)) is True
    assert le._deadline_passed(claimed_row(deadline=None)) is False


# ---------------------------------------------------------------------------
# Retry backoff
# ---------------------------------------------------------------------------


def test_backoff_doubles_and_caps() -> None:
    # rng=0.5 is the zero-jitter point, so the base delay is exact.
    def no_jitter() -> float:
        return 0.5

    assert [le._backoff_seconds(n, no_jitter) for n in (1, 2, 3)] == [30, 60, 120]
    assert le._backoff_seconds(0, no_jitter) == 30
    assert le._backoff_seconds(50, no_jitter) == le._RETRY_CAP_SECONDS


def test_backoff_jitter_is_bounded_and_stays_inside_the_cap() -> None:
    """Two erasures hitting one outage must not wake at the same instant."""
    low = le._backoff_seconds(1, lambda: 0.0)
    high = le._backoff_seconds(1, lambda: 1.0)
    assert low < 30 < high
    assert low >= int(30 * (1 - le._RETRY_JITTER_FRACTION))
    assert high <= int(30 * (1 + le._RETRY_JITTER_FRACTION))
    # At the cap the upper half is clamped, but the delay never exceeds it.
    assert le._backoff_seconds(50, lambda: 1.0) == le._RETRY_CAP_SECONDS
    assert le._backoff_seconds(50, lambda: 0.0) < le._RETRY_CAP_SECONDS


# ---------------------------------------------------------------------------
# Receipt identity
# ---------------------------------------------------------------------------


def test_receipt_params_are_deterministic_and_scoped_to_the_revision() -> None:
    params = le._receipt_params(erasure(), _outcome("objectstore", "verified"))
    assert params["idempotency_key"] == (
        "erase:00000000-0000-0000-0000-000000000002:"
        "00000000-0000-0000-0000-000000000003:2:objectstore"
    )
    assert params["status"] == "verified"
    assert params["error"] is None


# ---------------------------------------------------------------------------
# Session-event locators
# ---------------------------------------------------------------------------


async def test_session_event_locator_failure_is_permanent() -> None:
    with pytest.raises(le.PermanentErasureFailure):
        le._session_event_id("not-a-row-id")


def test_session_event_locator_parses_only_ascii_digits() -> None:
    assert le._session_event_id("42") == 42
    for bad in ("", "4 2", "-1", "²", "０４２", "42; DROP TABLE x"):
        with pytest.raises(RuntimeError):
            le._session_event_id(bad)
