"""Shared builders for the memory-lifecycle erasure unit tests.

Only what more than one test module needs lives here: the claimed-row and
``_Erasure`` builders, which the decisions, store-target, staging, and cache
modules all construct.

A fake with a single consumer stays next to the tests it drives — the Redis
double is in ``test_lifecycle_erasure_cache.py``, and the ``_stage``
replacements are in ``test_lifecycle_erasure_store_targets.py`` — so no module
carries a helper for a subject it does not test.

Not a test module: the name does not match ``test_*.py``, so pytest never
collects it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.config import Settings
from app.tasks.lifecycle_erasure import _ClaimedRow, _Erasure


def claimed_row(
    *,
    deadline: datetime | None = None,
    attempts: int = 1,
    event_type: str = "forgotten",
) -> _ClaimedRow:
    """One leased outbox row, with the identifiers the tests assert on."""
    return _ClaimedRow(
        row_id="00000000-0000-0000-0000-000000000001",
        org_id="00000000-0000-0000-0000-000000000002",
        memory_id="00000000-0000-0000-0000-000000000003",
        revision=2,
        attempts=attempts,
        event_type=event_type,
        deadline=deadline,
    )


def erasure(
    *,
    settings: Any | None = None,
    row: _ClaimedRow | None = None,
    job_deadline: float | None = None,
) -> _Erasure:
    """A claimed row plus the dependencies its store stages need."""
    return _Erasure(
        row=row or claimed_row(),
        settings=settings
        or Settings(
            lifecycle_erasure_job_timeout_seconds=900.0,
            lifecycle_erasure_store_timeout_seconds=120.0,
        ),
        factory=object(),
        job_deadline=job_deadline,
    )
