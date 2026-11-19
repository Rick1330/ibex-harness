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
class _ErasureState:
    """What one tenant read learned about the memory's erasure.

    Read under one ``session_as_app_org`` transaction so refs, receipts, the
    memory's agent and the organization purge's verdict all come from the same
    tenant fence and the same connection.
    """

    #: Recorded artifact locators, grouped by store.
    refs: dict[str, tuple[str, ...]]
    #: Receipts an earlier run already wrote for this revision, by store.
    receipts: dict[str, str]
    #: ``memories.agent_id``; ``None`` when the memory row is gone.
    agent_id: str | None
    #: The organization deletion's Redis verdict for this org, if the saga has
    #: recorded one. Only a ``purged`` row reads it.
    org_redis_purge: str | None = None


@dataclass(frozen=True, slots=True)
class _Erasure:
    """A claimed row plus the dependencies its store stages need."""

    row: _ClaimedRow
    settings: Any
    factory: Any
    #: ``memories.agent_id`` for the claim's memory. Only the cache stages need
    #: it, to derive the per-agent hot key for a pre-000078 row that recorded no
    #: cache ref. ``None`` means the memory row is gone; a ``purged`` row then
    #: falls back to the organization purge's verdict instead of claiming an
    #: absence nobody checked.
    agent_id: str | None = None
    #: The organization purge's Redis receipt status. An org-wide purge deletes
    #: every ``{org}:hot_memories:*`` key, so a ``verified`` receipt is real
    #: evidence that a purged memory's hot member is gone even though its agent
    #: (and therefore its derived key) no longer exists.
    org_redis_purge: str | None = None


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
