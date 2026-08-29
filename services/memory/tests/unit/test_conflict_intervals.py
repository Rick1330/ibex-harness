"""Unit tests for half-open validity interval overlap."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.conflict.intervals import ValidityInterval, intervals_overlap


def _dt(month: int, day: int = 1) -> datetime:
    return datetime(2026, month, day, tzinfo=UTC)


def test_adjacent_half_open_no_overlap() -> None:
    left = ValidityInterval(valid_from=_dt(3), valid_until=_dt(6))
    right = ValidityInterval(valid_from=_dt(6), valid_until=None)
    assert intervals_overlap(left, right) is False


def test_open_ended_overlap_when_newer_starts_inside() -> None:
    older = ValidityInterval(valid_from=_dt(3), valid_until=None)
    newer = ValidityInterval(valid_from=_dt(6), valid_until=None)
    assert intervals_overlap(older, newer) is True


def test_disjoint_closed_intervals() -> None:
    a = ValidityInterval(valid_from=_dt(1), valid_until=_dt(2))
    b = ValidityInterval(valid_from=_dt(3), valid_until=_dt(4))
    assert intervals_overlap(a, b) is False


def test_rejects_until_not_after_from() -> None:
    valid_from = _dt(6)
    valid_until = _dt(3)
    with pytest.raises(ValueError, match="valid_until"):
        ValidityInterval(valid_from=valid_from, valid_until=valid_until)


def test_naive_datetimes_become_utc() -> None:
    interval = ValidityInterval(
        valid_from=datetime(2026, 3, 1),  # noqa: DTZ001 — intentional naive input
        valid_until=datetime(2026, 6, 1),  # noqa: DTZ001 — intentional naive input
    )
    assert interval.valid_from.tzinfo is not None
    assert interval.valid_until is not None
    assert interval.valid_until.tzinfo is not None


def test_aware_non_utc_converted() -> None:
    from datetime import timedelta, timezone

    eastern = timezone(timedelta(hours=-5))
    interval = ValidityInterval(valid_from=datetime(2026, 3, 1, tzinfo=eastern))
    assert interval.valid_from.tzinfo == UTC
