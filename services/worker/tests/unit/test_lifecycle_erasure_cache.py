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
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace

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
_MARKER_KEY = (
    "00000000-0000-0000-0000-000000000002:memory_forgotten:"
    "00000000-0000-0000-0000-000000000003"
)
# The claimed row's memory, and a second memory sharing the agent's hot set.
_MEMBER = "00000000-0000-0000-0000-000000000003"
_OTHER_MEMBER = "00000000-0000-0000-0000-00000000000f"


class _FakeRedis:
    """Just enough of the async Redis surface the cache stages use.

    It holds the store rather than a set of canned answers: ``delete`` takes the
    key and every member of the sorted set it names, ``zrem`` takes one member.
    A stage that reached for the wrong verb therefore loses the wrong data here
    exactly as it would in Redis. ``unapplied`` names the keys and members whose
    removal the store has not caught up with — the survivor a stage must report
    as ``failed`` instead of assuming gone.
    """

    def __init__(
        self,
        *,
        live_keys: Iterable[str] = (),
        live_members: dict[str, Iterable[str]] | None = None,
        unapplied: Iterable[str] = (),
    ) -> None:
        self.deleted: list[str] = []
        self.zremoved: list[tuple[str, str]] = []
        self.markers: list[tuple[str, str, int | None]] = []
        self.ops: list[tuple[str, str]] = []
        self.polls: list[tuple[str, str]] = []
        self.closed = False
        self.live_keys = set(live_keys)
        self.live_members = {
            key: set(members) for key, members in (live_members or {}).items()
        }
        self.unapplied = set(unapplied)

    async def set(self, key: str, value: str, *, ex: int | None = None) -> bool:
        self.markers.append((key, value, ex))
        self.ops.append(("set", key))
        self.live_keys.add(key)
        return True

    async def delete(self, *keys: str) -> int:
        self.deleted.extend(keys)
        self.ops.append(("delete", keys[0]))
        removed = 0
        for key in keys:
            if key in self.unapplied:
                continue
            removed += 1 if key in self.live_keys else 0
            self.live_keys.discard(key)
            # DEL of a sorted set takes every member it holds, which is why the
            # hot stage may only ZREM the one member.
            self.live_members.pop(key, None)
        return removed

    async def exists(self, *keys: str) -> int:
        self.polls.append(("exists", keys[0]))
        return sum(1 for key in keys if key in self.live_keys)

    async def zrem(self, key: str, member: str) -> int:
        self.zremoved.append((key, member))
        self.ops.append(("zrem", key))
        if member in self.unapplied:
            return 0
        members = self.live_members.setdefault(key, set())
        if member not in members:
            return 0
        members.discard(member)
        return 1

    async def zscore(self, key: str, member: str) -> float | None:
        self.polls.append(("zscore", key))
        return 1.0 if member in self.live_members.get(key, set()) else None

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

    await le._stage(_cache_target("cache", _OBJECT_KEY), erasure(), time.monotonic() + 5)

    assert fake.markers == [(_MARKER_KEY, "1", le._CACHE_FORGOTTEN_TTL_SECONDS)]
    assert fake.deleted == [_OBJECT_KEY]
    assert fake.ops[0] == ("set", _MARKER_KEY), (
        "the marker must precede the delete, or a delayed write can restore the entry"
    )
    assert fake.closed, "the stage must not leak its client"


@pytest.mark.asyncio
async def test_forgotten_key_stays_inside_the_tenant_namespace() -> None:
    assert le._forgotten_key(_OBJECT_KEY) == (
        "00000000-0000-0000-0000-000000000002:memory_forgotten:"
        "00000000-0000-0000-0000-000000000003"
    )


# ---------------------------------------------------------------------------
# A store that does not let go
# ---------------------------------------------------------------------------


def _entry_purged(fake: _FakeRedis) -> None:
    """What only the ``cache`` rows prove: the entry was DELed, marker first."""
    assert fake.markers == [(_MARKER_KEY, "1", le._CACHE_FORGOTTEN_TTL_SECONDS)]
    assert fake.deleted == [_OBJECT_KEY], "the entry is the disclosure; it must be DELed"
    assert fake.zremoved == [], "a cache entry is deleted, not un-scored"


def _member_purged(fake: _FakeRedis) -> None:
    """What only the ``cache_hot`` row proves: one ZREM, the rest of the set intact."""
    assert fake.zremoved == [(_HOT_KEY, _MEMBER)]
    assert fake.deleted == [], "DEL of the hot key would evict live memories"
    assert _OTHER_MEMBER in fake.live_members[_HOT_KEY], (
        "one memory's forget must not take another memory's membership with it"
    )


@dataclass(frozen=True)
class _SurvivorCase:
    """One stage, one survivor, and the verdict that survivor earns.

    ``budget_seconds`` is the deadline handed to the stage, relative to the call:
    a negative one is already spent, so the stage must fail on its first look
    rather than sleep out a budget it does not have. ``waits`` marks the rows
    whose survivor must be given the budget before it is declared. ``check``
    holds the assertions only this row can make — the stores differ, so the
    proof that the right verb ran differs with them.
    """

    store: str
    locator: str
    budget_seconds: float
    check: Callable[[_FakeRedis], None]
    live_keys: frozenset[str] = frozenset()
    live_members: tuple[tuple[str, frozenset[str]], ...] = ()
    unapplied: frozenset[str] = frozenset()
    waits: bool = False


_ENTRY_SURVIVES = _SurvivorCase(
    store="cache",
    locator=_OBJECT_KEY,
    budget_seconds=-1.0,
    check=_entry_purged,
    live_keys=frozenset({_OBJECT_KEY}),
    unapplied=frozenset({_OBJECT_KEY}),
)

_HOT_MEMBER_SURVIVES = _SurvivorCase(
    store="cache_hot",
    locator=_HOT_KEY,
    budget_seconds=0.05,
    check=_member_purged,
    live_members=((_HOT_KEY, frozenset({_MEMBER, _OTHER_MEMBER})),),
    unapplied=frozenset({_MEMBER}),
    waits=True,
)


_SURVIVOR_CASES = [
    pytest.param(_ENTRY_SURVIVES, id="cache-entry-survives-spent-budget"),
    pytest.param(
        replace(_ENTRY_SURVIVES, budget_seconds=0.05, waits=True),
        id="cache-entry-survives-after-waiting",
    ),
    pytest.param(_HOT_MEMBER_SURVIVES, id="cache-hot-member-survives-after-waiting"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _SURVIVOR_CASES)
async def test_cache_stage_fails_when_the_store_survives(
    case: _SurvivorCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A surviving copy is a failed store, never a verified one.

    Each row runs the real stage against a store that has not applied the
    removal, and asserts the failure *and* the row's own proof that the right
    verb ran against the right key. The wait is asserted only where a budget was
    left: a spent one must not sleep.
    """
    fake = _FakeRedis(
        live_keys=case.live_keys,
        live_members=dict(case.live_members),
        unapplied=case.unapplied,
    )
    monkeypatch.setattr(le.staging, "_redis_client", lambda _settings: fake)
    started = time.monotonic()

    failed = False
    try:
        await le._stage(
            _cache_target(case.store, case.locator),
            erasure(),
            started + case.budget_seconds,
        )
    except TimeoutError:
        failed = True

    # The row's own check runs before the verdict: a stage that reached for the
    # wrong verb can make a survivor disappear and still look like a pass, and
    # the row that knows the verb is the one that can say so.
    case.check(fake)
    assert failed, "a surviving copy is failed, never verified"
    assert fake.closed, "the stage must not leak its client"
    if case.waits:
        assert len(fake.polls) >= 2, "the stage must look again before giving up"
        assert time.monotonic() - started >= 0.05, "the survivor was not waited out"
    else:
        assert len(fake.polls) == 1, "a spent budget must fail on the first look"


# ---------------------------------------------------------------------------
# The hot sorted set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hot_stage_removes_the_member_and_never_deletes_the_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The hot set belongs to the agent; only this memory's member may leave."""
    fake = _FakeRedis(live_members={_HOT_KEY: {_MEMBER, _OTHER_MEMBER}})
    monkeypatch.setattr(le.staging, "_redis_client", lambda _settings: fake)

    await le._stage(_cache_target("cache_hot", _HOT_KEY), erasure(), time.monotonic() + 5)

    assert fake.zremoved == [(_HOT_KEY, _MEMBER)]
    assert fake.deleted == [], "DEL of the hot key would evict live memories"
    assert fake.live_members[_HOT_KEY] == {_OTHER_MEMBER}, (
        "only the forgotten memory's member leaves the set"
    )


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
