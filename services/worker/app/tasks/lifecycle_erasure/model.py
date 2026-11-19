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
    #: cache ref. ``None`` means the memory row is gone; a ``purged`` row whose
    #: organization saga predates the hot-ref insert then has no address at all.
    agent_id: str | None = None
    #: The organization purge's Redis receipt status, read for a ``purged`` row
    #: only. It is a topology fact (``not_applicable`` means Redis is not
    #: deployed, so no hot set exists) and never proof of one member's absence:
    #: the org-wide delete ran at some instant, and a delayed hot write can land
    #: after it. The per-member proof is the address the saga records before it
    #: deletes the memory row.
    org_redis_purge: str | None = None
    #: Monotonic instant this row's job must finish by. Every object-store HEAD
    #: the proof path issues is capped by what is left of it, so a slow store
    #: cannot spend the budget the cache stores at the end of the row still need.
    job_deadline: float | None = None


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
class _DurableProof:
    """What a stored receipt still settles, and whether the store contradicted it.

    ``settled`` is the stored status when no later run has invalidated it, else
    ``None`` and the store is staged again. ``invalidated`` is set only when the
    recheck found positive evidence of a live copy: that is the one case where a
    newer outcome may replace an existing ``verified`` receipt. An unanswered
    recheck stages the store but invalidates nothing, because an outage is not
    evidence the object came back.
    """

    settled: str | None = None
    invalidated: bool = False


@dataclass(frozen=True, slots=True)
class _StoreOutcome:
    """What one store proved, and whether this run is what proved it."""

    store: str
    status: str
    error: str | None = None
    fresh: bool = True
    permanent: bool = False
    #: A live copy was observed for a store whose receipt said ``verified``, so
    #: this outcome may replace that proof even though it is weaker. Without it,
    #: a re-delete that fails would leave ``verified`` standing over a store that
    #: holds a copy.
    invalidates_proof: bool = False
