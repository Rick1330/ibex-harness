"""Pure decision rules of the erasure consumer.

They take values in and return a verdict, so they can be read and tested without
a database, Redis, or a clock. The sweep supplies the state and performs the
I/O; this module decides what that state means.

Two distinctions are load-bearing and must never blur:

* ``verified`` requires the store to have confirmed absence; an unreachable store
  is ``failed``, and ``not_applicable`` means only "this memory has no copy in
  that store".
* ``complete`` requires every store to be ``verified`` or ``not_applicable``;
  anything else is ``partial`` (retry) or, when a locator can never succeed or
  the deadline passed, terminal ``failed``.
"""

from __future__ import annotations

import random
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from .constants import (
    _ERROR_MAX_CHARS,
    _RETRY_BASE_SECONDS,
    _RETRY_CAP_SECONDS,
    _RETRY_JITTER_FRACTION,
    RECEIPT_STORES,
    SATISFIED_RECEIPT_STATUSES,
)
from .model import (
    PermanentErasureFailure,
    _ClaimedRow,
    _Erasure,
    _StoreOutcome,
    _StoreTarget,
)


def _stores_to_stage(refs: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    """Stores this run settles: the provable set, plus any store a ref names.

    A store outside ``RECEIPT_STORES`` has no producer recording its refs, so an
    absent ref says nothing about whether a copy exists and must not become a
    ``not_applicable`` receipt. A ref that *does* name it is a different fact: the
    copy is known to exist, so it is staged and receipted like any other store,
    and a failure there blocks ``complete``.
    """
    return tuple(dict.fromkeys((*RECEIPT_STORES, *sorted(refs))))


def _receipt_already_proves(proven: str | None, locators: tuple[str, ...]) -> bool:
    """Whether a receipt an earlier run wrote already settles this store.

    The durable proof is checked before the empty-locator case. A retry can
    legitimately see no locators for a store a previous run already proved (a
    store the earlier run cleared), and reporting ``not_applicable`` there would
    overwrite a ``verified`` receipt with a weaker one and drop its timestamp.

    ``not_applicable`` is kept only while there is still nothing to erase. A ref
    that appeared after that receipt is a copy that exists, so it is staged like
    any other: the weaker receipt must not hide a real copy.
    """
    if proven == "verified":
        return True
    return proven == "not_applicable" and not locators


def _erasure_state(outcomes: list[_StoreOutcome]) -> str:
    """``complete`` only when every store is verified or not applicable."""
    if all(outcome.status in SATISFIED_RECEIPT_STATUSES for outcome in outcomes):
        return "complete"
    return "partial"


def _outbox_state(outcomes: list[_StoreOutcome], row: _ClaimedRow) -> str:
    """The outbox state these outcomes earn, before any retry is scheduled.

    ``complete`` only when every store is proved. A locator that cannot succeed
    on retry, or a deadline that has passed, is terminally ``failed`` so the row
    stops waking; anything else is ``partial`` and retries with backoff.
    """
    if _erasure_state(outcomes) == "complete":
        return "complete"
    if _has_permanent_failure(outcomes) or _deadline_passed(row):
        return "failed"
    return "partial"


def _has_permanent_failure(outcomes: list[_StoreOutcome]) -> bool:
    """Whether any store failed in a way the next sweep cannot fix."""
    return any(outcome.permanent for outcome in outcomes)


def _deadline_passed(row: _ClaimedRow) -> bool:
    return row.deadline is not None and row.deadline <= datetime.now(tz=UTC)


def _backoff_seconds(attempts: int, rng: Any = random.random) -> int:
    """Capped exponential retry delay with bounded, injected jitter.

    ``rng`` is a callable returning ``[0, 1)``; the default is
    ``random.random`` and the tests inject a deterministic source. The jitter
    stays inside ``_RETRY_CAP_SECONDS`` so two erasures hitting the same outage
    do not wake at the same instant.
    """
    exponent = max(attempts - 1, 0)
    base = min(_RETRY_BASE_SECONDS * (2**exponent), _RETRY_CAP_SECONDS)
    jitter = _RETRY_JITTER_FRACTION * (2.0 * rng() - 1.0)
    return max(0, min(_RETRY_CAP_SECONDS, int(base * (1.0 + jitter))))


def _error_reason(exc: BaseException) -> str:
    """Short, content-free reason: a locator is an address, never memory text."""
    return f"{type(exc).__name__}: {exc}"[:_ERROR_MAX_CHARS]


def _session_event_id(locator: str) -> int:
    """Parse a ``session_events.id`` locator without echoing it.

    ``locator`` is caller-written text (``ibex_app`` holds INSERT on
    ``memory_artifact_refs``), so ``int(locator)`` would put the raw value into a
    ``ValueError`` message, and that message is written to the receipt's ``error``
    column and to the log. The failure is fixed text for the same reason.
    """
    if not (locator.isascii() and locator.isdigit()):
        raise PermanentErasureFailure("session_event locator is not a row id")
    return int(locator)


def _receipt_params(erasure: _Erasure, outcome: _StoreOutcome) -> dict[str, Any]:
    row = erasure.row
    return {
        "org_id": row.org_id,
        "memory_id": row.memory_id,
        "revision": row.revision,
        "store": outcome.store,
        "status": outcome.status,
        "idempotency_key": (
            f"erase:{row.org_id}:{row.memory_id}:{row.revision}:{outcome.store}"
        ),
        "error": outcome.error,
    }


def _failed_outcome(store: str, error: str) -> _StoreOutcome:
    return _StoreOutcome(store=store, status="failed", error=error)


def _failed_target(target: _StoreTarget, error: str) -> _StoreOutcome:
    """A permanent failure for a target whose address cannot be computed."""
    return replace(_failed_outcome(target.store, error), permanent=True)
