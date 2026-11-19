"""Unit tests for the memory-lifecycle erasure consumer's decision rules.

The rules pinned here are the ones a receipt cannot be trusted without:
``complete`` means every store was proven, an unreachable store is never
``verified``, a store already proven is not staged again, and the SQL the claim
runs names the same event types the Python constant does. The store stages
themselves are exercised against real PostgreSQL and ClickHouse in
``tests/integration/test_memory_lifecycle_erasure_postgres.py``.
"""

from __future__ import annotations

import inspect
import pathlib
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

import app.tasks  # noqa: F401 — registers the task with the Celery app
from app.config import Settings
from app.tasks import lifecycle_erasure as le
from app.tasks.lifecycle_erasure import (
    ERASURE_EVENT_TYPES,
    RECEIPT_STORES,
    SATISFIED_RECEIPT_STATUSES,
    _ClaimedRow,
    _Erasure,
    _StoreOutcome,
    _StoreTarget,
)


def _row(*, deadline: datetime | None = None, attempts: int = 1) -> _ClaimedRow:
    return _ClaimedRow(
        row_id="00000000-0000-0000-0000-000000000001",
        org_id="00000000-0000-0000-0000-000000000002",
        memory_id="00000000-0000-0000-0000-000000000003",
        revision=2,
        attempts=attempts,
        event_type="forgotten",
        deadline=deadline,
    )


def _erasure(*, settings: Any | None = None, row: _ClaimedRow | None = None) -> _Erasure:
    return _Erasure(
        row=row or _row(),
        settings=settings
        or Settings(
            lifecycle_erasure_job_timeout_seconds=900.0,
            lifecycle_erasure_store_timeout_seconds=120.0,
        ),
        factory=object(),
    )


def _outcome(store: str, status: str) -> _StoreOutcome:
    return _StoreOutcome(store=store, status=status)


def _three_stores(clickhouse: str) -> list[_StoreOutcome]:
    """One outcome per store the consumer stages, with ClickHouse varied."""
    return [
        _outcome("objectstore", "verified"),
        _outcome("clickhouse", clickhouse),
        _outcome("session_event", "verified"),
    ]


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
        _erasure(), target, existing, time.monotonic() + deadline_seconds
    )


#: The migration that owns the claim function's event filter.
_CLAIM_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[4]
    / "infra/migrations/postgres/000074_memory_lifecycle_erasure_state.up.sql"
)


# ---------------------------------------------------------------------------
# Job state
# ---------------------------------------------------------------------------


def test_state_is_complete_when_every_store_is_satisfied() -> None:
    assert le._erasure_state(_three_stores("not_applicable")) == "complete"


@pytest.mark.parametrize("status", ["failed", "pending"])
def test_state_is_partial_when_any_store_is_unproven(status: str) -> None:
    assert le._erasure_state(_three_stores(status)) == "partial"


def test_not_applicable_is_satisfied_but_not_verified() -> None:
    """The two statuses are distinct facts and must stay distinct."""
    assert "not_applicable" in SATISFIED_RECEIPT_STATUSES
    assert "verified" in SATISFIED_RECEIPT_STATUSES
    assert "failed" not in SATISFIED_RECEIPT_STATUSES
    assert "pending" not in SATISFIED_RECEIPT_STATUSES


def test_deadline_passed_only_after_the_recorded_deadline() -> None:
    future = datetime.now(tz=UTC) + timedelta(seconds=60)
    past = datetime.now(tz=UTC) - timedelta(seconds=1)
    assert le._deadline_passed(_row(deadline=future)) is False
    assert le._deadline_passed(_row(deadline=past)) is True
    assert le._deadline_passed(_row(deadline=None)) is False


# ---------------------------------------------------------------------------
# Retry backoff
# ---------------------------------------------------------------------------


def test_backoff_doubles_and_caps() -> None:
    # rng=0.5 is the zero-jitter point, so the base delay is exact.
    def no_jitter() -> float:
        return 0.5

    assert [le._backoff_seconds(n, no_jitter) for n in (1, 2, 3)] == [30, 60, 120]
    assert le._backoff_seconds(0, no_jitter) == 30
    assert le._backoff_seconds(50, no_jitter) == le._RETRY_CAP_SECONDS


def test_backoff_jitter_is_bounded_and_stays_inside_the_cap() -> None:
    """Two erasures hitting one outage must not wake at the same instant."""
    low = le._backoff_seconds(1, lambda: 0.0)
    high = le._backoff_seconds(1, lambda: 1.0)
    assert low < 30 < high
    assert low >= int(30 * (1 - le._RETRY_JITTER_FRACTION))
    assert high <= int(30 * (1 + le._RETRY_JITTER_FRACTION))
    # At the cap the upper half is clamped, but the delay never exceeds it.
    assert le._backoff_seconds(50, lambda: 1.0) == le._RETRY_CAP_SECONDS
    assert le._backoff_seconds(50, lambda: 0.0) < le._RETRY_CAP_SECONDS


# ---------------------------------------------------------------------------
# Receipt identity
# ---------------------------------------------------------------------------


def test_receipt_params_are_deterministic_and_scoped_to_the_revision() -> None:
    erasure = _erasure()
    params = le._receipt_params(erasure, _outcome("objectstore", "verified"))
    assert params["idempotency_key"] == (
        "erase:00000000-0000-0000-0000-000000000002:"
        "00000000-0000-0000-0000-000000000003:2:objectstore"
    )
    assert params["status"] == "verified"
    assert params["error"] is None


# ---------------------------------------------------------------------------
# Store decisions that need no I/O
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
async def test_session_event_locator_failure_is_permanent() -> None:
    with pytest.raises(le.PermanentErasureFailure):
        le._session_event_id("not-a-row-id")


@pytest.mark.asyncio
async def test_store_stage_that_times_out_is_failed_never_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(le.sweep, "_stage", _stage_that_raises(TimeoutError()))
    outcome = await _erase(
        _StoreTarget("clickhouse", ("00000000-0000-0000-0000-00000000000a",)), {}
    )
    assert (outcome.status, outcome.error) == ("failed", "store_timeout")


@pytest.mark.asyncio
async def test_unknown_store_fails_closed_instead_of_falling_through() -> None:
    with pytest.raises(RuntimeError, match="no erasure stage"):
        await le._stage(
            _StoreTarget("filesystem", ("/tmp/x",)), _erasure(), time.monotonic() + 1
        )


@pytest.mark.asyncio
async def test_session_event_locator_must_be_a_row_id() -> None:
    """A locator that is not a bigint cannot name a session_events row.

    The refusal is fixed text: the locator is caller-written, and anything it
    carries would otherwise reach the receipt's ``error`` column and the log.
    """
    locator = "not-a-row-id"
    with pytest.raises(RuntimeError, match="not a row id") as refused:
        await le._stage_session_events((locator,), _erasure(), time.monotonic() + 1)
    assert locator not in str(refused.value)


def test_session_event_locator_parses_only_ascii_digits() -> None:
    assert le._session_event_id("42") == 42
    for bad in ("", "4 2", "-1", "²", "０４２", "42; DROP TABLE x"):
        with pytest.raises(RuntimeError):
            le._session_event_id(bad)


# ---------------------------------------------------------------------------
# Store coverage: what is provable, and what a ref can still force
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
    assert set(staged) == {"objectstore", "session_event", "cache", "cache_hot", "clickhouse"}
    # Deterministic order: the provable set first, then ref-named stores sorted.
    assert staged == (
        "objectstore",
        "session_event",
        "cache",
        "cache_hot",
        "clickhouse",
    )


def test_store_targets_derive_the_cache_keys_an_absent_ref_cannot_name() -> None:
    """A pre-000078 row records no cache ref; the keys are still derivable.

    Treating the absent ref as ``not_applicable`` left a live Redis copy nothing
    ever swept. The derived address is what makes the erasure reach it.
    """
    row = _row()
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
            {"cache": ("recorded-object-key",)}, "agent-1", _row()
        )
    }
    assert targets["cache"].locators == ("recorded-object-key",)
    assert targets["cache"].derived is False


def test_store_targets_mark_the_hot_key_underivable_without_the_agent() -> None:
    """Without the memory row the hot key cannot be derived; that is not absence."""
    targets = {
        target.store: target for target in le._store_targets({}, None, _row())
    }
    assert targets["cache_hot"].underivable is True
    assert targets["cache"].underivable is False


@pytest.mark.asyncio
async def test_underivable_cache_address_fails_permanently() -> None:
    """A missing agent is a property of the row, so a retry cannot fix it."""
    outcome = await le._erase_store(
        _erasure(),
        _StoreTarget("cache_hot", (), underivable=True),
        {},
        time.monotonic() + 5,
    )
    assert (outcome.status, outcome.permanent) == ("failed", True)
    assert "not derivable" in (outcome.error or "")


#: The memory service's key definitions, which the worker cannot import.
_MEMORY_KEYS = (
    pathlib.Path(__file__).resolve().parents[4]
    / "services/memory/app/cache/memory_keys.py"
)


def test_cache_guard_constants_match_the_memory_service() -> None:
    """The two services must agree on the marker, or the guard protects nothing.

    The worker cannot import ``app.cache.memory_keys`` (a different deployment),
    so the namespace and the marker lifetime are duplicated deliberately and this
    contract test is what keeps the copies equal.
    """
    import ast

    def literal(node: ast.AST) -> object:
        """Fold a constant or a ``*`` of constants; refuse anything else."""
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            return literal(node.left) * literal(node.right)  # type: ignore[operator]
        raise ValueError("not a literal")

    tree = ast.parse(_MEMORY_KEYS.read_text(encoding="utf-8"))
    values: dict[str, object] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            values[node.targets[0].id] = literal(node.value)
    assert values["MEMORY_FORGOTTEN_NAMESPACE"] == le._CACHE_FORGOTTEN_NAMESPACE
    assert values["MEMORY_FORGOTTEN_TTL_SECONDS"] == le._CACHE_FORGOTTEN_TTL_SECONDS


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
        _erasure(),
        _StoreTarget("objectstore", ()),
        {"objectstore": "verified"},
        time.monotonic() + 10,
    )
    assert (outcome.status, outcome.fresh) == ("verified", False)


@pytest.mark.asyncio
async def test_object_store_stage_waits_until_head_reports_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    present = {"s3://bucket/one.json"}

    def delete(uri: str, *, org_id: str, settings: Any | None = None) -> None:
        del org_id, settings
        present.discard(uri)

    def exists(uri: str, *, org_id: str, settings: Any | None = None) -> bool:
        del org_id, settings
        return uri in present

    monkeypatch.setattr(le.staging, "delete_uri", delete)
    monkeypatch.setattr(le.staging, "object_exists", exists)
    await le._stage_objectstore(
        ("s3://bucket/one.json",), _erasure(), time.monotonic() + 10
    )
    assert present == set()


@pytest.mark.asyncio
async def test_object_store_stage_raises_when_the_object_survives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A delete the store accepted but did not apply is not an erasure."""
    monkeypatch.setattr(
        le.staging, "delete_uri", lambda uri, *, org_id, settings=None: None
    )
    monkeypatch.setattr(
        le.staging, "object_exists", lambda uri, *, org_id, settings=None: True
    )
    with pytest.raises(TimeoutError):
        await le._stage_objectstore(
            ("s3://bucket/one.json",), _erasure(), time.monotonic() + 0.1
        )


# ---------------------------------------------------------------------------
# Contract guards: SQL, task registration, configuration
# ---------------------------------------------------------------------------


def test_claim_function_names_exactly_the_erasure_event_types() -> None:
    """The migration's SQL literal set and the Python constant must not drift.

    The event filter lives in the ``SECURITY DEFINER`` claim function, so the
    file is the contract: a Python constant that lists fewer types than the
    function is a comment, and one that lists more is a lie.
    """
    sql = " ".join(_CLAIM_MIGRATION.read_text(encoding="utf-8").split())
    for event_type in ERASURE_EVENT_TYPES:
        assert f"'{event_type}'" in sql, event_type
    for excluded in ("'created'", "'content_updated'", "'superseded'", "'quarantined'"):
        assert excluded not in sql, excluded


def test_claim_sql_goes_through_the_security_definer_function() -> None:
    sql = " ".join(le._CLAIM_SQL.split())
    assert "memory_lifecycle_claim_erasure" in sql
    # The outbox is RLS-scoped; a direct SELECT here would silently see nothing.
    assert "FROM ibex_core.memory_lifecycle_outbox" not in sql


def test_stage_table_covers_every_receipt_store() -> None:
    """Every store this consumer can prove has a stage, and every stage is known.

    ``_STAGE_BY_STORE`` is a superset of ``RECEIPT_STORES`` because a ref can name
    a store outside the provable set (ClickHouse) and it must still be erased;
    the key set is pinned so a new stage cannot appear without a decision here.
    """
    assert set(RECEIPT_STORES) <= set(le._STAGE_BY_STORE)
    assert set(le._STAGE_BY_STORE) == {
        "objectstore",
        "clickhouse",
        "session_event",
        "cache",
        "cache_hot",
    }


def test_event_scoped_clickhouse_op_binds_org_and_event() -> None:
    """The reused ClickHouse op narrows to one event and still binds the org."""
    from app.tasks import org_deletion_stores as stores

    op = stores.CHOp(
        stores.CHClient(http=object(), url="http://clickhouse/", auth=None),
        stores.CH_EVENT_TABLE,
        "00000000-0000-0000-0000-000000000002",
        event_id="00000000-0000-0000-0000-00000000000a",
    )
    query, params = stores._ch_statement(
        op, stores.CH_DELETE_QUERIES, stores.CH_EVENT_DELETE_QUERY
    )
    assert query == stores.CH_EVENT_DELETE_QUERY
    assert params["param_org_id"] == "00000000-0000-0000-0000-000000000002"
    assert params["param_event_id"] == "00000000-0000-0000-0000-00000000000a"


def test_event_scoped_clickhouse_op_refuses_another_table() -> None:
    """An event query paired with the wrong table would delete rows silently."""
    from app.tasks import org_deletion_stores as stores

    op = stores.CHOp(
        stores.CHClient(http=object(), url="http://clickhouse/", auth=None),
        "llm_traces",
        "00000000-0000-0000-0000-000000000002",
        event_id="00000000-0000-0000-0000-00000000000a",
    )
    with pytest.raises(ValueError, match="evidence table"):
        stores._ch_statement(op, stores.CH_DELETE_QUERIES, stores.CH_EVENT_DELETE_QUERY)


def test_object_exists_raises_when_the_store_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreachable object store must never read as "the object is gone"."""
    from app import objectstore_client

    monkeypatch.delenv("S3_ENDPOINT", raising=False)
    with pytest.raises(RuntimeError, match="S3_ENDPOINT"):
        objectstore_client.object_exists("s3://bucket/org/key.json", org_id="org")


def test_settle_statements_carry_the_org_predicate() -> None:
    """RLS is one defence; AGENTS.md §4.1 requires the explicit predicate too."""
    for name in ("_COMPLETE_SQL", "_RETRY_SQL", "_FAIL_SQL", "_RETIRE_STALE_SQL"):
        sql = " ".join(getattr(le, name).split())
        assert "org_id = CAST(:org_id AS uuid)" in sql, name


def test_sql_is_literal_not_built_from_values() -> None:
    sources = [
        inspect.getsource(module) for module in (le.sql, le.staging, le.sweep)
    ]
    for source in sources:
        assert 'f"DELETE' not in source
        assert "f'DELETE" not in source
        assert 'f"UPDATE' not in source
        assert "f'UPDATE" not in source


def test_task_registration_and_time_limits() -> None:
    from app.celery_app import route_for_task
    from app.task_names import TASK_LIFECYCLE_ERASE_MEMORY

    assert le.erase_memory.name == TASK_LIFECYCLE_ERASE_MEMORY
    # The decorator applied the derivation from the settings loaded at import.
    assert le.erase_memory.soft_time_limit == le._ERASURE_SOFT_LIMIT
    assert le.erase_memory.time_limit == le._ERASURE_TIME_LIMIT
    assert le._ERASURE_SOFT_LIMIT == le._task_limits(900.0)[0]
    from app.celery_app import create_celery_app

    celery = create_celery_app(
        Settings(
            broker_url="redis://localhost:6379/1",
            result_backend="redis://localhost:6379/3",
            env="development",
        )
    )
    assert route_for_task(celery, TASK_LIFECYCLE_ERASE_MEMORY) == "maintenance"
    assert "lifecycle-erase-memory" in (celery.conf.beat_schedule or {})


def test_task_limits_cover_a_non_default_job_budget() -> None:
    """A legal 1800 s budget must not be killed by a fixed 900 s task limit."""
    original = (le.erase_memory.soft_time_limit, le.erase_memory.time_limit)
    try:
        le.configure_erasure_task_limits(1800.0)
        assert le.erase_memory.soft_time_limit >= 1800.0
        assert le.erase_memory.soft_time_limit == int(
            1800.0 + le._ERASURE_SETTLEMENT_HEADROOM_SECONDS
        )
        assert le.erase_memory.time_limit > le.erase_memory.soft_time_limit
    finally:
        le.erase_memory.soft_time_limit, le.erase_memory.time_limit = original


def test_deadline_defaults_match_the_contract() -> None:
    settings = Settings()
    assert settings.lifecycle_erasure_store_timeout_seconds == 120.0
    assert settings.lifecycle_erasure_job_timeout_seconds == 900.0


@pytest.mark.asyncio
async def test_sweep_skips_without_a_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.delenv("IBEX_WORKER_DATABASE_URL", raising=False)
    out = await le._run_sweep(settings=Settings(database_url=None))
    assert out == {"status": "skipped", "reason": "missing_dsn"}


# ---------------------------------------------------------------------------
# Cache stages
# ---------------------------------------------------------------------------
#
# Redis is real in ``tests/integration/test_memory_cache_erasure_postgres.py``.
# Here the client is a stub only so the stage's decision rules can be driven
# without a server: what it refuses, what verb it applies, and when it refuses to
# call a surviving copy "gone".


class _FakeRedis:
    """Just enough of the async Redis surface the cache stages use."""

    def __init__(
        self,
        *,
        surviving_keys: set[str] | None = None,
        surviving_members: set[str] | None = None,
    ) -> None:
        self.deleted: list[str] = []
        self.zremoved: list[tuple[str, str]] = []
        self.markers: list[tuple[str, str, int | None]] = []
        self.ops: list[tuple[str, str]] = []
        self.closed = False
        self._surviving_keys = surviving_keys or set()
        self._surviving_members = surviving_members or set()

    async def set(self, key: str, value: str, *, ex: int | None = None) -> bool:
        self.markers.append((key, value, ex))
        self.ops.append(("set", key))
        return True

    async def delete(self, *keys: str) -> int:
        self.deleted.extend(keys)
        self.ops.append(("delete", keys[0]))
        return len(keys)

    async def exists(self, *keys: str) -> int:
        return sum(1 for key in keys if key in self._surviving_keys)

    async def zrem(self, key: str, member: str) -> int:
        self.zremoved.append((key, member))
        self.ops.append(("zrem", key))
        return 1

    async def zscore(self, key: str, member: str) -> float | None:
        return 1.0 if member in self._surviving_members else None

    async def aclose(self) -> None:
        self.closed = True


def _cache_target(store: str, locator: str) -> _StoreTarget:
    return _StoreTarget(store, (locator,))


@pytest.mark.asyncio
async def test_cache_stage_deletes_the_entry_and_waits_for_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The content-bearing entry is deleted and the stage only returns when gone.

    The forgotten marker is written first: a delayed after-commit create must
    lose to an erasure even when its write lands after this stage's absence
    check.
    """
    fake = _FakeRedis()
    monkeypatch.setattr(le.staging, "_redis_client", lambda _settings: fake)
    key = "00000000-0000-0000-0000-000000000002:memory:00000000-0000-0000-0000-000000000003"
    marker = "00000000-0000-0000-0000-000000000002:memory_forgotten:00000000-0000-0000-0000-000000000003"

    await le._stage(_cache_target("cache", key), _erasure(), time.monotonic() + 5)

    assert fake.markers == [(marker, "1", le._CACHE_FORGOTTEN_TTL_SECONDS)]
    assert fake.deleted == [key]
    assert fake.ops[0] == ("set", marker), (
        "the marker must precede the delete, or a delayed write can restore the entry"
    )
    assert fake.closed, "the stage must not leak its client"


@pytest.mark.asyncio
async def test_forgotten_key_stays_inside_the_tenant_namespace() -> None:
    key = "00000000-0000-0000-0000-000000000002:memory:00000000-0000-0000-0000-000000000003"
    assert le._forgotten_key(key) == (
        "00000000-0000-0000-0000-000000000002:memory_forgotten:"
        "00000000-0000-0000-0000-000000000003"
    )


@pytest.mark.asyncio
async def test_cache_stage_fails_when_the_entry_survives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A surviving cache entry is a failed store, never a verified one."""
    key = "00000000-0000-0000-0000-000000000002:memory:00000000-0000-0000-0000-000000000003"
    fake = _FakeRedis(surviving_keys={key})
    monkeypatch.setattr(le.staging, "_redis_client", lambda _settings: fake)

    with pytest.raises(TimeoutError):
        await le._stage(_cache_target("cache", key), _erasure(), time.monotonic() - 1)


@pytest.mark.asyncio
async def test_cache_stage_waits_before_declaring_a_survivor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A store that answers late is given its budget, then reported failed."""
    key = "00000000-0000-0000-0000-000000000002:memory:00000000-0000-0000-0000-000000000003"
    fake = _FakeRedis(surviving_keys={key})
    monkeypatch.setattr(le.staging, "_redis_client", lambda _settings: fake)

    with pytest.raises(TimeoutError):
        await le._stage(
            _cache_target("cache", key), _erasure(), time.monotonic() + 0.01
        )


@pytest.mark.asyncio
async def test_cache_hot_stage_fails_when_the_member_survives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hot member that stays scored is a failed store, never verified."""
    key = "00000000-0000-0000-0000-000000000002:hot_memories:00000000-0000-0000-0000-000000000004"
    fake = _FakeRedis(surviving_members={"00000000-0000-0000-0000-000000000003"})
    monkeypatch.setattr(le.staging, "_redis_client", lambda _settings: fake)

    with pytest.raises(TimeoutError):
        await le._stage(
            _cache_target("cache_hot", key), _erasure(), time.monotonic() + 0.01
        )


def test_cache_key_requires_a_tenant() -> None:
    """An empty org cannot be a cache namespace, so it is refused before Redis."""
    with pytest.raises(le.PermanentErasureFailure, match="tenant id required"):
        le._cache_key("cache", "some:memory:key", org_id="")


@pytest.mark.asyncio
async def test_cache_hot_stage_removes_the_member_and_never_deletes_the_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The hot set belongs to the agent; only this memory's member may leave."""
    fake = _FakeRedis()
    monkeypatch.setattr(le.staging, "_redis_client", lambda _settings: fake)
    key = "00000000-0000-0000-0000-000000000002:hot_memories:00000000-0000-0000-0000-000000000004"

    await le._stage(_cache_target("cache_hot", key), _erasure(), time.monotonic() + 5)

    assert fake.zremoved == [(key, "00000000-0000-0000-0000-000000000003")]
    assert fake.deleted == [], "DEL of the hot key would evict live memories"


@pytest.mark.asyncio
async def test_cache_locator_outside_the_namespace_is_a_permanent_failure() -> None:
    """A ref naming ``{org}:directive:...`` cannot become valid on a retry."""
    outcome = await le._stage_store(
        _erasure(),
        _cache_target(
            "cache", "00000000-0000-0000-0000-000000000002:directive:live"
        ),
        time.monotonic() + 5,
    )

    assert outcome.status == "failed"
    assert outcome.permanent is True


@pytest.mark.asyncio
async def test_cache_stage_without_a_redis_url_is_failed_not_verified() -> None:
    """A deployment with no cache cannot prove a ref-named cache store."""
    from types import SimpleNamespace

    key = "00000000-0000-0000-0000-000000000002:memory:00000000-0000-0000-0000-000000000003"
    no_cache = _Erasure(
        row=_row(),
        settings=SimpleNamespace(
            redis_url=None, lifecycle_erasure_store_timeout_seconds=20.0
        ),
        factory=object(),
    )

    outcome = await le._stage_store(
        no_cache, _cache_target("cache", key), time.monotonic() + 5
    )

    assert outcome.status == "failed"
    assert "redis" in (outcome.error or "").lower()
