"""Value objects shared by the erasure consumer's stages.

They are deliberately dumb: a claimed row, the dependencies one run needs, one
store's targets, and what a store proved. Keeping them here lets the staging,
decision and sweep modules depend on the same shapes without importing each
other.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


class PermanentErasureFailure(RuntimeError):
    """A locator that cannot succeed on retry.

    An unsupported scheme, a malformed locator, or a key outside the tenant
    prefix is a property of the stored address, not a transient outage. Retrying
    it until ``erasure_deadline`` only delays the honest ``failed`` state, so the
    consumer records the failure and stops scheduling attempts.
    """


@dataclass(frozen=True, slots=True)
class _ClaimedRow:
    """One leased outbox row, as the claim function returned it."""

    row_id: str
    org_id: str
    memory_id: str
    revision: int
    attempts: int
    event_type: str
    deadline: datetime | None


@dataclass(frozen=True, slots=True)
class _Erasure:
    """A claimed row plus the dependencies its store stages need."""

    row: _ClaimedRow
    settings: Any
    factory: Any
    #: ``memories.agent_id`` for the claim's memory. Only the cache stages need
    #: it, to derive the per-agent hot key for a pre-000078 row that recorded no
    #: cache ref. ``None`` means the memory row is gone and the hot address
    #: cannot be derived, which is a permanent failure, never "nothing to erase".
    agent_id: str | None = None


@dataclass(frozen=True, slots=True)
class _StoreTarget:
    """One store and the locators this run will erase for it."""

    store: str
    locators: tuple[str, ...]
    #: The locators were derived from the memory's identifiers because no ref
    #: recorded them, not read from ``memory_artifact_refs``.
    derived: bool = False
    #: A cache store whose keys could not be derived (the memory row is gone).
    #: Absence cannot be proved, so the store fails permanently.
    underivable: bool = False


@dataclass(frozen=True, slots=True)
class _StoreOutcome:
    """What one store proved, and whether this run is what proved it."""

    store: str
    status: str
    error: str | None = None
    fresh: bool = True
    permanent: bool = False
