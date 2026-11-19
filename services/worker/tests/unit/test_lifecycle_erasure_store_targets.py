"""Unit tests for store selection: which stores a run settles, and with what.

Two rules a receipt cannot be trusted without live here:

* a store is only settled when its absence is *provable* — ``RECEIPT_STORES``
  names the stores whose producer records a ref for every copy, and a ref that
  names a store outside that set is staged anyway because the copy is known;
* a cache store with no recorded ref is not ``not_applicable`` — its keys are
  derivable from ``(org, agent, memory)``, and an address that cannot be derived
  fails permanently rather than claiming absence nobody checked.

Everything below runs without I/O: the per-store decision is a verdict on
targets and receipts, and the stage itself is replaced wherever it would run.
The stages are covered in ``test_lifecycle_erasure_staging.py`` and
``..._cache.py``; the sweep's claim/settle half in ``..._sweep.py``.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from app.tasks import lifecycle_erasure as le
from app.tasks.lifecycle_erasure import RECEIPT_STORES, _StoreOutcome, _StoreTarget
from tests.unit.lifecycle_erasure_fakes import claimed_row, erasure


def _stage_that_raises(exc: BaseException) -> Any:
    """A ``_stage`` replacement that fails the way a broken store does."""

    async def stage(*_args: Any, **_kwargs: Any) -> None:
        raise exc

    return stage


def _stage_must_not_run(monkeypatch: pytest.MonkeyPatch, message: str) -> None:
    """Make staging this store fail the test instead of running."""
    monkeypatch.setattr(le.sweep, "_stage", _stage_that_raises(AssertionError(message)))


async def _erase(
    target: _StoreTarget,
    existing: dict[str, str],
    *,
    deadline_seconds: float = 10.0,
) -> _StoreOutcome:
    """Run one store decision with a job deadline relative to now."""
    return await le._erase_store(
        erasure(), target, existing, time.monotonic() + deadline_seconds
    )


# ---------------------------------------------------------------------------
# What is provable, and what a ref can still force
# ---------------------------------------------------------------------------


def test_clickhouse_is_not_a_provable_store() -> None:
    """No producer records a per-memory ClickHouse locator, so no claim is made.

    A receipt saying ``not_applicable`` for ClickHouse would certify an erasure
    nobody performed, so the store is out of ``RECEIPT_STORES`` and is only
    settled when a ref names one.
    """
    assert "clickhouse" not in RECEIPT_STORES
    assert set(RECEIPT_STORES) == {
        "objectstore",
        "session_event",
        "cache",
        "cache_hot",
    }


def test_stores_to_stage_adds_ref_named_stores_only() -> None:
    """A store with no ref and no producer is never staged (no false receipt)."""
    assert le._stores_to_stage({}) == RECEIPT_STORES
    assert le._stores_to_stage({"objectstore": ("s3://b/o/a.json",)}) == RECEIPT_STORES
    staged = le._stores_to_stage(
        {"objectstore": ("s3://b/o/a.json",), "clickhouse": ("event-1",)}
    )
    assert set(staged) == {
        "objectstore",
        "session_event",
        "cache",
        "cache_hot",
        "clickhouse",
    }
    # Deterministic order: the provable set first, then ref-named stores sorted.
    assert staged == (
        "objectstore",
        "session_event",
        "cache",
        "cache_hot",
        "clickhouse",
    )


# ---------------------------------------------------------------------------
# Store targets: the address each store is reached at
# ---------------------------------------------------------------------------


def test_store_targets_derive_the_cache_keys_an_absent_ref_cannot_name() -> None:
    """A pre-000078 row records no cache ref; the keys are still derivable.

    Treating the absent ref as ``not_applicable`` left a live Redis copy nothing
    ever swept. The derived address is what makes the erasure reach it.
    """
    row = claimed_row()
    targets = {
        target.store: target for target in le._store_targets({}, "agent-1", row)
    }

    assert targets["cache"].locators == (f"{row.org_id}:memory:{row.memory_id}",)
    assert targets["cache"].derived is True
    assert targets["cache_hot"].locators == (
        f"{row.org_id}:hot_memories:agent-1",
    )
    assert targets["cache_hot"].derived is True
    assert targets["objectstore"].locators == ()
    assert targets["objectstore"].derived is False


def test_store_targets_keep_a_recorded_cache_ref() -> None:
    """A recorded ref is the address; derivation does not second-guess it."""
    targets = {
        target.store: target
        for target in le._store_targets(
            {"cache": ("recorded-object-key",)}, "agent-1", claimed_row()
        )
    }
    assert targets["cache"].locators == ("recorded-object-key",)
    assert targets["cache"].derived is False


def test_store_targets_mark_the_hot_key_underivable_without_the_agent() -> None:
    """Without the memory row the hot key cannot be derived; that is not absence."""
    targets = {
        target.store: target for target in le._store_targets({}, None, claimed_row())
    }
    assert targets["cache_hot"].underivable is True
    assert targets["cache"].underivable is False


@pytest.mark.asyncio
async def test_underivable_cache_address_fails_permanently() -> None:
    """A missing agent is a property of the row, so a retry cannot fix it."""
    outcome = await le._erase_store(
        erasure(),
        _StoreTarget("cache_hot", (), underivable=True),
        {},
        time.monotonic() + 5,
    )
    assert (outcome.status, outcome.permanent) == ("failed", True)
    assert "not derivable" in (outcome.error or "")


# ---------------------------------------------------------------------------
# One store's decision, before any I/O
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_without_locators_is_not_applicable_and_touches_nothing() -> None:
    outcome = await _erase(_StoreTarget("objectstore", ()), {})
    assert (outcome.status, outcome.fresh) == ("not_applicable", True)


@pytest.mark.asyncio
async def test_store_already_proven_is_not_staged_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stage_must_not_run(monkeypatch, "a satisfied store must not be staged again")
    outcome = await _erase(
        _StoreTarget("objectstore", ("s3://bucket/one.json",)),
        {"objectstore": "verified"},
    )
    assert (outcome.status, outcome.fresh) == ("verified", False)


@pytest.mark.asyncio
async def test_not_applicable_does_not_hide_a_ref_that_appeared_later(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A weaker durable receipt must not survive a copy that now exists.

    ``not_applicable`` is only true while there is nothing to erase. If a ref
    arrives after that receipt was written, the copy is real and must be staged —
    otherwise the earlier "no copy here" would hide it forever.
    """
    staged: list[tuple[str, ...]] = []

    async def record(target: _StoreTarget, *_args: Any, **_kwargs: Any) -> None:
        staged.append(target.locators)

    monkeypatch.setattr(le.sweep, "_stage", record)
    outcome = await _erase(
        _StoreTarget("objectstore", ("s3://bucket/one.json",)),
        {"objectstore": "not_applicable"},
    )
    assert (outcome.status, outcome.fresh) == ("verified", True)
    assert staged == [("s3://bucket/one.json",)]


@pytest.mark.asyncio
async def test_store_already_proven_survives_a_later_run_with_no_locators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A durable ``verified`` receipt must not be downgraded to ``not_applicable``.

    The empty-locator branch used to run first, so a retry that saw no refs for a
    store already proven rewrote the receipt as ``not_applicable`` with a NULL
    timestamp — losing the only evidence that the store was cleared.
    """

    async def explode(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("a proven store must not be staged again")

    monkeypatch.setattr(le.sweep, "_stage", explode)
    outcome = await le._erase_store(
        erasure(),
        _StoreTarget("objectstore", ()),
        {"objectstore": "verified"},
        time.monotonic() + 10,
    )
    assert (outcome.status, outcome.fresh) == ("verified", False)


@pytest.mark.asyncio
async def test_store_beyond_the_job_deadline_is_failed_without_staging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stage_must_not_run(
        monkeypatch, "the job deadline must stop the store before it starts"
    )
    outcome = await _erase(
        _StoreTarget("clickhouse", ("00000000-0000-0000-0000-00000000000a",)),
        {},
        deadline_seconds=-1.0,
    )
    assert (outcome.status, outcome.error) == ("failed", "job_deadline_exceeded")


@pytest.mark.asyncio
async def test_store_stage_that_raises_is_failed_never_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        le.sweep, "_stage", _stage_that_raises(RuntimeError("s3 head capture/1.json: 503"))
    )
    outcome = await _erase(_StoreTarget("objectstore", ("s3://bucket/one.json",)), {})
    assert outcome.status == "failed"
    assert "503" in (outcome.error or "")


@pytest.mark.asyncio
async def test_store_validation_failure_is_classified_permanent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A locator that cannot change cannot succeed on the next sweep."""
    monkeypatch.setattr(
        le.sweep, "_stage", _stage_that_raises(ValueError("unsupported uri"))
    )
    outcome = await _erase(
        _StoreTarget("objectstore", ("https://example.invalid/archive",)), {}
    )
    assert (outcome.status, outcome.permanent) == ("failed", True)


@pytest.mark.asyncio
async def test_store_transport_failure_is_classified_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 5xx or an unreachable store is worth retrying; it is not permanent."""
    monkeypatch.setattr(
        le.sweep, "_stage", _stage_that_raises(RuntimeError("s3 head capture/1.json: 503"))
    )
    outcome = await _erase(_StoreTarget("objectstore", ("s3://bucket/one.json",)), {})
    assert outcome.permanent is False


@pytest.mark.asyncio
async def test_store_stage_that_times_out_is_failed_never_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(le.sweep, "_stage", _stage_that_raises(TimeoutError()))
    outcome = await _erase(
        _StoreTarget("clickhouse", ("00000000-0000-0000-0000-00000000000a",)), {}
    )
    assert (outcome.status, outcome.error) == ("failed", "store_timeout")
