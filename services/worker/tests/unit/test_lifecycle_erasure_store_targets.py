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
    monkeypatch.setattr(le.sweep, "object_exists", lambda *_args, **_kwargs: False)
    outcome = await _erase(
        _StoreTarget("objectstore", ("s3://bucket/one.json",)),
        {"objectstore": "verified"},
    )
    assert (outcome.status, outcome.fresh) == ("verified", False)


@pytest.mark.asyncio
async def test_verified_cache_receipt_is_not_rechecked_with_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cache stores are fenced by the forgotten marker, not by a HEAD call."""
    _stage_must_not_run(monkeypatch, "a fenced cache store must not be staged again")

    def unexpected(*_args: Any, **_kwargs: Any) -> bool:
        raise AssertionError("only the object store is re-checked")

    monkeypatch.setattr(le.sweep, "object_exists", unexpected)
    outcome = await _erase(
        _StoreTarget("cache", ("org:memory:00000000-0000-0000-0000-000000000003",)),
        {"cache": "verified"},
    )
    assert (outcome.status, outcome.fresh) == ("verified", False)


@pytest.mark.asyncio
@pytest.mark.parametrize("head", ["present", "error"])
async def test_verified_object_receipt_is_restaged_when_its_proof_no_longer_stands(
    monkeypatch: pytest.MonkeyPatch, head: str
) -> None:
    """A stored ``verified`` receipt is re-checked before it is trusted.

    The archive key is derived from ``(org, memory)``, so a late re-archive
    recreates exactly the object the receipt covered. A HEAD that reports the
    object, or that cannot answer at all, means the retry must delete it again
    instead of settling on the earlier proof.
    """
    staged: list[tuple[str, ...]] = []

    async def record(target: _StoreTarget, *_args: Any, **_kwargs: Any) -> None:
        staged.append(target.locators)

    def exists(*_args: Any, **_kwargs: Any) -> bool:
        if head == "error":
            raise RuntimeError("s3 down")
        return True

    monkeypatch.setattr(le.sweep, "_stage", record)
    monkeypatch.setattr(le.sweep, "object_exists", exists)
    outcome = await _erase(
        _StoreTarget("objectstore", ("s3://bucket/one.json",)),
        {"objectstore": "verified"},
    )
    assert (outcome.status, outcome.fresh) == ("verified", True)
    assert staged == [("s3://bucket/one.json",)]


def _slow_head(delay: float, *, found: bool = False) -> Any:
    """An object-store HEAD that takes ``delay`` seconds to answer."""

    def head(_uri: str, *, org_id: str, settings: Any = None) -> bool:
        del org_id, settings
        time.sleep(delay)
        return found

    return head


@pytest.mark.asyncio
async def test_expired_proof_head_restages_the_object_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A HEAD cut at its budget is unanswered, so the store is deleted again.

    The proof runs before the row's later stores. Left unbounded, one slow HEAD
    could consume the job budget those stores need; capped, it costs one bounded
    check and the store is staged, which is idempotent.
    """
    staged: list[tuple[str, ...]] = []

    async def record(target: _StoreTarget, *_args: Any, **_kwargs: Any) -> None:
        staged.append(target.locators)

    monkeypatch.setattr(le.sweep, "_stage", record)
    monkeypatch.setattr(le.sweep, "object_exists", _slow_head(0.2))
    monkeypatch.setattr(le.sweep, "_PROOF_HEAD_CAP_SECONDS", 0.02)
    started = time.monotonic()

    outcome = await le._erase_store(
        erasure(job_deadline=started + 5.0),
        _StoreTarget("objectstore", ("s3://bucket/one.json",)),
        {"objectstore": "verified"},
        started + 5.0,
    )

    assert (outcome.status, outcome.fresh) == ("verified", True)
    assert staged == [("s3://bucket/one.json",)], "an expired check must restage"
    assert time.monotonic() - started < 1.0, "the HEAD was not cut at its budget"


@pytest.mark.asyncio
async def test_proof_head_is_cut_by_the_job_deadline_as_well_as_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The budget is ``min(remaining, cap)``: a nearly spent job cuts the HEAD.

    With the cap left at its real value, only the deadline can stop this call in
    time, so an implementation that capped per call but ignored the deadline
    would hang for the full slow answer.
    """
    monkeypatch.setattr(le.sweep, "object_exists", _slow_head(0.5))
    started = time.monotonic()

    with pytest.raises(TimeoutError):
        await le._object_reappeared(
            erasure(job_deadline=started + 0.02), ("s3://bucket/one.json",)
        )

    assert time.monotonic() - started < 0.4, "the HEAD outlived the job deadline"


@pytest.mark.asyncio
async def test_proof_head_with_a_spent_budget_starts_no_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A check that cannot finish is not started at all.

    With the deadline already passed, the first locator must raise before any
    HEAD is issued rather than spending a call the row cannot wait for.
    """
    started: list[str] = []

    def head(uri: str, *, org_id: str, settings: Any = None) -> bool:
        del org_id, settings
        started.append(uri)
        return False

    monkeypatch.setattr(le.sweep, "object_exists", head)

    with pytest.raises(TimeoutError):
        await le._object_reappeared(
            erasure(job_deadline=time.monotonic() - 1.0),
            ("s3://bucket/one.json", "s3://bucket/two.json"),
        )

    assert started == [], "no HEAD may be started on a spent budget"


@pytest.mark.asyncio
async def test_proof_head_loop_stops_once_the_budget_is_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No later locator is started once the check cannot finish.

    Starting a HEAD it cannot wait for only leaks another call and delays the
    restage that is the honest answer.
    """
    calls: list[str] = []

    def head(uri: str, *, org_id: str, settings: Any = None) -> bool:
        del org_id, settings
        calls.append(uri)
        time.sleep(0.2)
        return False

    monkeypatch.setattr(le.sweep, "object_exists", head)
    monkeypatch.setattr(le.sweep, "_PROOF_HEAD_CAP_SECONDS", 0.02)

    with pytest.raises(TimeoutError):
        await le._object_reappeared(
            erasure(job_deadline=time.monotonic() + 5.0),
            ("s3://bucket/one.json", "s3://bucket/two.json", "s3://bucket/three.json"),
        )

    assert calls == ["s3://bucket/one.json"], "the loop must stop, not start another HEAD"


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
