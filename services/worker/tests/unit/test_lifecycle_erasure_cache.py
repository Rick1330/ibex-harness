"""Unit tests for the two cache stages and their key guards.

The cache is where a forgotten memory's text actually lives after the row is
tombstoned, so these are the stages whose failure is a disclosure. The client is
a stub here — Redis is real in
``tests/integration/test_memory_cache_erasure_postgres.py`` — and the rules it
lets us pin are: the forgotten marker is written *before* the delete, only the
member leaves a hot set, a surviving copy is ``failed`` and never ``verified``,
a locator outside the tenant namespace is refused permanently, and an
unconfigured Redis cannot prove anything.
"""

from __future__ import annotations

import time

import pytest

from app.tasks import lifecycle_erasure as le
from app.tasks.lifecycle_erasure import _Erasure, _StoreTarget
from tests.unit.lifecycle_erasure_fakes import claimed_row, erasure

_OBJECT_KEY = (
    "00000000-0000-0000-0000-000000000002:memory:00000000-0000-0000-0000-000000000003"
)
_HOT_KEY = (
    "00000000-0000-0000-0000-000000000002:hot_memories:"
    "00000000-0000-0000-0000-000000000004"
)


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


# ---------------------------------------------------------------------------
# The object cache entry
# ---------------------------------------------------------------------------


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
    marker = (
        "00000000-0000-0000-0000-000000000002:memory_forgotten:"
        "00000000-0000-0000-0000-000000000003"
    )

    await le._stage(_cache_target("cache", _OBJECT_KEY), erasure(), time.monotonic() + 5)

    assert fake.markers == [(marker, "1", le._CACHE_FORGOTTEN_TTL_SECONDS)]
    assert fake.deleted == [_OBJECT_KEY]
    assert fake.ops[0] == ("set", marker), (
        "the marker must precede the delete, or a delayed write can restore the entry"
    )
    assert fake.closed, "the stage must not leak its client"


@pytest.mark.asyncio
async def test_forgotten_key_stays_inside_the_tenant_namespace() -> None:
    assert le._forgotten_key(_OBJECT_KEY) == (
        "00000000-0000-0000-0000-000000000002:memory_forgotten:"
        "00000000-0000-0000-0000-000000000003"
    )


@pytest.mark.asyncio
async def test_cache_stage_fails_when_the_entry_survives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A surviving cache entry is a failed store, never a verified one."""
    fake = _FakeRedis(surviving_keys={_OBJECT_KEY})
    monkeypatch.setattr(le.staging, "_redis_client", lambda _settings: fake)

    with pytest.raises(TimeoutError):
        await le._stage(
            _cache_target("cache", _OBJECT_KEY), erasure(), time.monotonic() - 1
        )


@pytest.mark.asyncio
async def test_cache_stage_waits_before_declaring_a_survivor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A store that answers late is given its budget, then reported failed."""
    fake = _FakeRedis(surviving_keys={_OBJECT_KEY})
    monkeypatch.setattr(le.staging, "_redis_client", lambda _settings: fake)

    with pytest.raises(TimeoutError):
        await le._stage(
            _cache_target("cache", _OBJECT_KEY), erasure(), time.monotonic() + 0.01
        )


# ---------------------------------------------------------------------------
# The hot sorted set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hot_stage_fails_when_the_member_survives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hot member that stays scored is a failed store, never verified."""
    fake = _FakeRedis(surviving_members={"00000000-0000-0000-0000-000000000003"})
    monkeypatch.setattr(le.staging, "_redis_client", lambda _settings: fake)

    with pytest.raises(TimeoutError):
        await le._stage(
            _cache_target("cache_hot", _HOT_KEY), erasure(), time.monotonic() + 0.01
        )


@pytest.mark.asyncio
async def test_cache_hot_stage_removes_the_member_and_never_deletes_the_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The hot set belongs to the agent; only this memory's member may leave."""
    fake = _FakeRedis()
    monkeypatch.setattr(le.staging, "_redis_client", lambda _settings: fake)

    await le._stage(_cache_target("cache_hot", _HOT_KEY), erasure(), time.monotonic() + 5)

    assert fake.zremoved == [(_HOT_KEY, "00000000-0000-0000-0000-000000000003")]
    assert fake.deleted == [], "DEL of the hot key would evict live memories"


# ---------------------------------------------------------------------------
# The guards in front of Redis
# ---------------------------------------------------------------------------


def test_cache_key_requires_a_tenant() -> None:
    """An empty org cannot be a cache namespace, so it is refused before Redis."""
    with pytest.raises(le.PermanentErasureFailure, match="tenant id required"):
        le._cache_key("cache", "some:memory:key", org_id="")


@pytest.mark.asyncio
async def test_cache_locator_outside_the_namespace_is_a_permanent_failure() -> None:
    """A ref naming ``{org}:directive:...`` cannot become valid on a retry."""
    outcome = await le._stage_store(
        erasure(),
        _cache_target("cache", "00000000-0000-0000-0000-000000000002:directive:live"),
        time.monotonic() + 5,
    )

    assert outcome.status == "failed"
    assert outcome.permanent is True


@pytest.mark.asyncio
async def test_cache_stage_without_a_redis_url_is_failed_not_verified() -> None:
    """A deployment with no cache cannot prove a ref-named cache store."""
    from types import SimpleNamespace

    no_cache = _Erasure(
        row=claimed_row(),
        settings=SimpleNamespace(
            redis_url=None, lifecycle_erasure_store_timeout_seconds=20.0
        ),
        factory=object(),
    )

    outcome = await le._stage_store(
        no_cache, _cache_target("cache", _OBJECT_KEY), time.monotonic() + 5
    )

    assert outcome.status == "failed"
    assert "redis" in (outcome.error or "").lower()
