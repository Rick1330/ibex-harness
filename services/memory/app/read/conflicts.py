"""Unresolved-conflict suppression on the read path (milestone 5.B.2 / ADR-0094).

The milestone sketch says "two candidates joined by a ``contradicts`` edge and
no resolution: only the higher-scored one survives". In this codebase no
``contradicts`` edge is ever written -- ``insert_relationship`` has no
production caller -- so the authority for "unresolved conflict" is
``ibex_core.memory_conflict_escalations`` with ``status = 'pending'``. That is
what the conflict stage writes when it escalates instead of auto-superseding.

A memory can sit in more than one pending escalation, so hydration returns the
*set* of pending escalation ids per row and two rows conflict when their sets
intersect. That makes the rule pairwise and order-independent, and it needs no
extra round trip: the set is a correlated subquery on the hydration query
already being run.

The winner is decided by rank order. Within one conflict the caller keeps the
first (highest-ranked) hit and drops the rest, so the returned page can never
contain both sides of an unresolved contradiction.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from app.read.metrics import CONFLICT_SUPPRESSED
from app.read.models import MemorySearchResult


def conflict_groups_from_row(row: Mapping[str, object]) -> tuple[UUID, ...]:
    """Read the hydrated escalation-id array; tolerate a driver returning a list."""
    raw = row.get("conflict_groups")
    if raw is None:
        return ()
    return tuple(UUID(str(value)) for value in raw)  # type: ignore[union-attr]


def collapse_conflict_pairs(results: Sequence[MemorySearchResult]) -> list[MemorySearchResult]:
    """Drop every hit that conflicts with an already-kept, higher-ranked hit.

    Order carries the decision: callers pass ranked results. A hit with no
    pending escalation is always kept, so the common case costs one set lookup.

    Pure on purpose. The caller records the drops only for the list whose
    survivors it actually returns; a refill pass re-collapses an overlapping
    list, and counting both would roughly double the metric.
    """
    kept: list[MemorySearchResult] = []
    kept_groups: set[UUID] = set()
    for hit in results:
        if hit.conflict_groups and not kept_groups.isdisjoint(hit.conflict_groups):
            continue
        kept.append(hit)
        kept_groups.update(hit.conflict_groups)
    return kept


def record_suppressed(input_count: int, kept_count: int) -> None:
    """Count the drops that shaped the returned page."""
    dropped = input_count - kept_count
    if dropped > 0:
        CONFLICT_SUPPRESSED.inc(dropped)
