"""Store stages: the operations that prove one store absent.

Every stage must raise unless absence is confirmed. A stage that returned
success on "the delete was accepted" would turn a store refusal into a receipt
nobody earned, which is the failure this consumer exists to prevent.

The object store and ClickHouse stages talk to their clients; the session-event
and cache stages use PostgreSQL and Redis. The cache stages also write the
forgotten marker *before* deleting, so a write that was already in flight when
the forget ran cannot recreate the object after this stage observed it absent.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from sqlalchemy import text

from app.db import session_as_purge_org
from app.objectstore_client import delete_uri, object_exists
from app.tasks import org_deletion_stores as _stores

from .constants import (
    _CACHE_FORGOTTEN_NAMESPACE,
    _CACHE_FORGOTTEN_TTL_SECONDS,
    _CACHE_NAMESPACES,
)
from .decisions import _session_event_id
from .model import PermanentErasureFailure, _Erasure, _StoreTarget
from .sql import _COUNT_SESSION_EVENT_SQL, _DELETE_SESSION_EVENT_SQL


async def _stage(target: _StoreTarget, erasure: _Erasure, deadline: float) -> None:
    """Dispatch one store stage; every branch must raise unless absence is proven."""
    stage = _STAGE_BY_STORE.get(target.store)
    if stage is None:
        # Fail closed: a store the refs name but this module cannot erase must
        # never fall through to "nothing to do" and be reported verified.
        raise RuntimeError(f"no erasure stage for store {target.store!r}")
    await stage(target.locators, erasure, deadline)


async def _stage_objectstore(
    locators: tuple[str, ...], erasure: _Erasure, deadline: float
) -> None:
    """Delete each archived object and wait until HEAD reports it gone.

    The org is passed to the object-store client, not inferred from the URI: a
    ref row is caller-written text, so a locator naming another tenant's key must
    be refused rather than honoured.
    """
    org_id = erasure.row.org_id
    for uri in locators:
        await asyncio.to_thread(
            delete_uri, uri, org_id=org_id, settings=erasure.settings
        )
    for uri in locators:
        await _wait_object_absent(uri, org_id, erasure.settings, deadline)


async def _wait_object_absent(
    uri: str, org_id: str, settings: Any, deadline: float
) -> None:
    while True:
        if not await asyncio.to_thread(
            object_exists, uri, org_id=org_id, settings=settings
        ):
            return
        if time.monotonic() >= deadline:
            raise TimeoutError("object-store object is still present after delete")
        await asyncio.sleep(0.5)


async def _stage_clickhouse(
    locators: tuple[str, ...], erasure: _Erasure, deadline: float
) -> None:
    """Delete each recorded evidence event and wait for the mutation to land."""
    if not _stores.clickhouse_configured(erasure.settings):
        # Deployed but unreachable is a failure, never "nothing to erase".
        raise RuntimeError("clickhouse is unreachable (no CLICKHOUSE_DSN configured)")
    for event_id in locators:
        await _stores.delete_clickhouse_event(
            erasure.settings,
            org_id=erasure.row.org_id,
            event_id=event_id,
            deadline=deadline,
        )


async def _stage_session_events(
    locators: tuple[str, ...], erasure: _Erasure, deadline: float
) -> None:
    """Delete each recorded capture event row and confirm it is gone.

    ``ibex_app`` holds no DELETE on ``session_events``: that table is the
    append-only audit trail, and the request-path identity must not be able to
    remove an event without a forget, a receipt and a legal-hold check. The verb
    belongs to ``ibex_purge`` (000064), so this one stage borrows that identity
    for the row's own org — the same fence, a narrower verb.
    """
    del deadline  # the caller's wait_for is the budget for a synchronous delete
    event_ids = [_session_event_id(locator) for locator in locators]
    params = [
        {"org_id": erasure.row.org_id, "event_id": event_id} for event_id in event_ids
    ]
    async with session_as_purge_org(erasure.factory, erasure.row.org_id) as session:
        for bound in params:
            await session.execute(text(_DELETE_SESSION_EVENT_SQL), bound)
        for bound in params:
            if await session.scalar(text(_COUNT_SESSION_EVENT_SQL), bound):
                raise RuntimeError("session_event row is still present after delete")


async def _stage_cache(
    locators: tuple[str, ...], erasure: _Erasure, deadline: float
) -> None:
    """Delete each cached memory object and wait until EXISTS reports it gone.

    The object entry carries the memory's ``content``; this is the store whose
    stale copy is the disclosure. The forgotten marker is written before the
    delete: a create that committed before its after-commit write can run at any
    time, including now, and without the marker that write would recreate the
    object this stage just removed. DEL is idempotent, so a retry after a partial
    failure and a redelivery of the same revision are both safe.
    """
    client = _redis_client(erasure.settings)
    try:
        keys = [
            _cache_key("cache", locator, org_id=erasure.row.org_id)
            for locator in locators
        ]
        for key in keys:
            await client.set(
                _forgotten_key(key), "1", ex=_CACHE_FORGOTTEN_TTL_SECONDS
            )
        await client.delete(*keys)
        await _wait_cache_keys_absent(client, keys, deadline, "cache entry")
    finally:
        await client.aclose()


async def _stage_cache_hot(
    locators: tuple[str, ...], erasure: _Erasure, deadline: float
) -> None:
    """Fence the memory, remove its member from each hot set, then confirm it.

    ZREM of one member, never DEL of the key: the key belongs to the agent and
    holds every hot memory's score. Deleting it would erase live state for
    memories this forget has nothing to do with.

    The forgotten marker is written before the ZREM and is what makes the
    absence durable. The hot write is a guarded ZADD that refuses while the
    marker exists (``services/memory/app/cache/hot_write.py``), so a create that
    committed before its ``refresh_hot`` and whose write lands after this stage
    cannot re-add the member. Without it, a ZREM that was correct when it ran
    could be undone a millisecond later — the org-wide purge has the same
    shape, and its receipt is not a substitute for this fence.
    """
    client = _redis_client(erasure.settings)
    member = erasure.row.memory_id
    try:
        keys = [
            _cache_key("cache_hot", locator, org_id=erasure.row.org_id)
            for locator in locators
        ]
        await client.set(
            _hot_forgotten_key(erasure.row.org_id, member),
            "1",
            ex=_CACHE_FORGOTTEN_TTL_SECONDS,
        )
        for key in keys:
            await client.zrem(key, member)
        await _wait_cache_member_absent(client, keys, member, deadline)
    finally:
        await client.aclose()


def _cache_key(store: str, locator: str, *, org_id: str) -> str:
    """Refuse a cache locator outside this store's tenant namespace.

    The message is fixed and never echoes the locator: a ref row is
    caller-written, so the value is attacker-influenced and it reaches both the
    receipt's ``error`` column and the worker log.
    """
    if not org_id:
        raise PermanentErasureFailure("tenant id required for cache access")
    prefix = f"{org_id}:{_CACHE_NAMESPACES[store]}:"
    if not locator.startswith(prefix):
        raise PermanentErasureFailure("cache locator is outside the tenant namespace")
    return locator


def _forgotten_key(object_key: str) -> str:
    """The marker key that fences a delayed write out of an erased object key.

    The object locator is ``<org>:memory:<id>`` and the memory id is a uuid, so
    the namespace occurs once and the replacement is unambiguous. The locator has
    already passed ``_cache_key``, so it is inside this row's tenant namespace.
    """
    return object_key.replace(
        f":{_CACHE_NAMESPACES['cache']}:", f":{_CACHE_FORGOTTEN_NAMESPACE}:", 1
    )


def _hot_forgotten_key(org_id: str, memory_id: str) -> str:
    """The same marker, built from the row because a hot locator names the agent.

    The two cache stores are fenced by one per-memory marker: the hot write's
    ZADD script checks it before adding a member, so the marker a hot stage
    writes also stops a delayed object write, which is the same memory.
    """
    return f"{org_id}:{_CACHE_FORGOTTEN_NAMESPACE}:{memory_id}"


def _redis_client(settings: Any) -> Any:
    """An async Redis client for the erasure stage, or a fail-closed refusal.

    A ref that names a cache store while this deployment has no Redis URL is a
    deployment that cannot prove the store: reporting ``verified`` would be a
    claim nobody checked, so the stage raises and the receipt says ``failed``.
    """
    redis_url = getattr(settings, "redis_url", None)
    if not redis_url:
        raise RuntimeError("redis is unreachable (no REDIS_URL configured)")
    from redis.asyncio import Redis

    return Redis.from_url(
        redis_url, socket_connect_timeout=5.0, socket_timeout=5.0
    )


async def _wait_cache_keys_absent(
    client: Any, keys: list[str], deadline: float, what: str
) -> None:
    """Wait until no key exists, or fail rather than report a stale copy gone."""
    while await client.exists(*keys):
        if time.monotonic() >= deadline:
            raise TimeoutError(f"{what} is still present after delete")
        await asyncio.sleep(0.1)


async def _wait_cache_member_absent(
    client: Any, keys: list[str], member: str, deadline: float
) -> None:
    """Wait until no sorted set still scores this member."""
    while await _member_still_scored(client, keys, member):
        if time.monotonic() >= deadline:
            raise TimeoutError("hot cache member is still present after zrem")
        await asyncio.sleep(0.1)


async def _member_still_scored(client: Any, keys: list[str], member: str) -> bool:
    """Whether any of the sorted sets still scores ``member``."""
    for key in keys:
        if await client.zscore(key, member) is not None:
            return True
    return False


# Store name to stage. A store missing here fails closed rather than silently
# reporting absence; ``test_lifecycle_erasure_contract`` pins the key set to
# ``RECEIPT_STORES``.
_STAGE_BY_STORE = {
    "objectstore": _stage_objectstore,
    "clickhouse": _stage_clickhouse,
    "session_event": _stage_session_events,
    "cache": _stage_cache,
    "cache_hot": _stage_cache_hot,
}
