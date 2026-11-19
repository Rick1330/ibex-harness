"""Unit tests for the Redis failure classification the cache stages rely on.

A cache stage runs against Redis, and the two services that touch those keys are
separate deployment units: the memory service owns the retryability rule, and the
worker mirrors it because neither image ships the other's code. ``app`` is the
same top-level package name in both, so importing across is not an option either.

The contract test at the bottom is what keeps the mirror honest: it loads the
memory service's module *by file path* and executes both implementations against
every exception class ``redis.exceptions`` defines. A list that drifts, a tuple
that loses a member, or a rule that changes the default fails here, not in a
production retry loop.

The behaviour tests pin what the erasure decision needs: an authentication or
wrong-type refusal is permanent (the row settles ``failed`` after one attempt),
while a timeout or a dropped connection retries.
"""

from __future__ import annotations

import importlib.util
import inspect
import pathlib
import time
from types import ModuleType
from typing import Any

import pytest
from redis.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ClusterDownError,
    DataError,
    MasterDownError,
    RedisError,
    ResponseError,
    TryAgainError,
)
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
)
from redis.exceptions import (
    TimeoutError as RedisTimeoutError,
)

from app.tasks import lifecycle_erasure as le
from app.tasks.lifecycle_erasure import _StoreTarget, redis_failures
from app.tasks.lifecycle_erasure.model import PermanentErasureFailure
from tests.unit.lifecycle_erasure_fakes import claimed_row, erasure

#: The canonical classification, owned by the memory service.
_MEMORY_REDIS_FAILURES = (
    pathlib.Path(__file__).resolve().parents[4]
    / "services/memory/app/cache/redis_failures.py"
)

_TARGET = _StoreTarget("cache", ("key",))


@pytest.mark.parametrize(
    "error",
    [
        AuthenticationError("bad password"),
        AuthorizationError("denied"),
        DataError("client refusal"),
        ResponseError("WRONGTYPE Operation against a key holding the wrong kind"),
    ],
)
def test_a_refusal_is_permanent(error: BaseException) -> None:
    """A refusal cannot succeed on the next attempt, however long the row waits."""
    assert redis_failures.is_permanent_redis_failure(error) is True


@pytest.mark.parametrize(
    "error",
    [
        RedisTimeoutError("slow"),
        RedisConnectionError("down"),
        ClusterDownError("failover"),
        TryAgainError("retry"),
        MasterDownError("failover"),
        OSError("socket closed"),
    ],
)
def test_an_outage_is_retryable(error: BaseException) -> None:
    assert redis_failures.is_permanent_redis_failure(error) is False


def test_non_redis_errors_are_left_to_the_existing_classification() -> None:
    """The Redis rule must not turn a ClickHouse or object-store error permanent."""
    assert (
        redis_failures.is_permanent_redis_failure(RuntimeError("clickhouse down"))
        is False
    )


def test_worker_permanent_rule_composes_the_redis_rule() -> None:
    """``_is_permanent`` keeps its locator rule and adds the Redis one."""
    assert le.sweep._is_permanent(PermanentErasureFailure("bad locator")) is True
    assert le.sweep._is_permanent(ValueError("unsupported uri")) is True
    assert le.sweep._is_permanent(AuthenticationError("bad password")) is True
    assert le.sweep._is_permanent(RedisTimeoutError("slow")) is False
    assert le.sweep._is_permanent(RuntimeError("s3 down")) is False


@pytest.mark.asyncio
async def test_an_auth_failure_settles_the_row_failed_without_a_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An expired password is a deployment fact, not a transient outage."""

    async def auth_failure(*_args: Any, **_kwargs: Any) -> None:
        raise AuthenticationError("WRONGPASS invalid username-password pair")

    monkeypatch.setattr(le.sweep, "_stage", auth_failure)

    outcome = await le._stage_store(erasure(), _TARGET, time.monotonic() + 5.0)

    assert (outcome.status, outcome.permanent) == ("failed", True)
    assert outcome.error is not None
    assert le._outbox_state([outcome], claimed_row()) == "failed"


def test_the_worker_lists_match_the_memory_service_exactly() -> None:
    """The two declared lists are the same classes, not merely equivalent prose."""
    memory = _load_memory_failures()
    assert set(memory._NON_RETRYABLE_REDIS_FAILURES) == set(redis_failures._REFUSALS)
    assert set(memory._RETRYABLE_REDIS_FAILURES) == set(redis_failures._OUTAGES)


def test_every_redis_exception_class_gets_the_same_verdict() -> None:
    """Execute both implementations across the whole ``redis.exceptions`` surface.

    A class the worker treats as permanent while the memory service retries it
    (or the reverse) is the divergence the finding is about, so it fails here
    rather than surfacing as two services disagreeing about one outage.
    """
    memory = _load_memory_failures()
    compared = 0
    for exc_type in _redis_error_classes():
        error = _probe(exc_type)
        if error is None:
            continue
        assert redis_failures.is_permanent_redis_failure(error) is (
            not memory.is_retryable_redis_failure(error)
        ), exc_type.__name__
        compared += 1
    assert compared >= 20, "the matrix must cover the real hierarchy, not a stub"


def _load_memory_failures() -> ModuleType:
    """Load the memory service's module by path: it imports only redis."""
    spec = importlib.util.spec_from_file_location(
        "memory_redis_failures", _MEMORY_REDIS_FAILURES
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _redis_error_classes() -> tuple[type[BaseException], ...]:
    """Every ``redis.exceptions`` class that subclasses ``RedisError``."""
    import redis.exceptions as rex

    return tuple(
        sorted(
            {
                cls
                for _, cls in inspect.getmembers(rex, inspect.isclass)
                if issubclass(cls, RedisError) and cls.__module__ == rex.__name__
            },
            key=lambda cls: cls.__name__,
        )
    )


def _probe(exc_type: type[BaseException]) -> BaseException | None:
    """Instance a class with a message, or with no arguments, or not at all."""
    for args in (("probe",), ()):
        try:
            return exc_type(*args)
        except (TypeError, ValueError):
            continue
    return None
