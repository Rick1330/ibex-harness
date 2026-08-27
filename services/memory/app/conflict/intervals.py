"""Half-open validity interval helpers (ADR-0047 / ADR-0056)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

# Sentinel for open-ended valid_until (NULL in Postgres).
_OPEN = datetime.max.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class ValidityInterval:
    """World-time interval [valid_from, valid_until); None until = open."""

    valid_from: datetime
    valid_until: datetime | None = None

    def __post_init__(self) -> None:
        start = _as_utc(self.valid_from)
        object.__setattr__(self, "valid_from", start)
        if self.valid_until is not None:
            end = _as_utc(self.valid_until)
            if end <= start:
                msg = "valid_until must be > valid_from"
                raise ValueError(msg)
            object.__setattr__(self, "valid_until", end)

    @property
    def end_exclusive(self) -> datetime:
        if self.valid_until is None:
            return _OPEN
        return self.valid_until


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def intervals_overlap(left: ValidityInterval, right: ValidityInterval) -> bool:
    """True when half-open intervals share any instant."""
    return left.valid_from < right.end_exclusive and right.valid_from < left.end_exclusive
