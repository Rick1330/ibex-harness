"""Redis object cache + hot sorted-set writes (m3.C.5 / ADR-0057)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BusyLoadingError,
    ClusterDownError,
    DataError,
    MasterDownError,
    RedisError,
    TryAgainError,
)
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
)
from redis.exceptions import (
    TimeoutError as RedisTimeoutError,
)

from app.cache.hot_score import compute_hot_cache_score
from app.cache.hot_write import HotZaddRequest, register_hot_zadd_trim_script, zadd_hot_memory
from app.cache.memory_keys import (
    MEMORY_FORGOTTEN_TTL_SECONDS,
    memory_forgotten_key,
    memory_hot_key,
    memory_object_key,
)
from app.config import Settings
from app.write.metrics import WRITE_CACHE_ERRORS
from app.write.models import MemoryRow, WriteOutcome, WriteOutcomeKind

logger = logging.getLogger(__name__)

_OBJECT_TTL = 3600

#: Check-and-set as one Redis evaluation. A read followed by a separate ``SET``
#: leaves the window A1 describes: the marker can appear (a forget, or the
#: worker) between the check and the write. Redis runs a script atomically, so
#: either the marker exists when the script runs and nothing is written, or the
#: script writes and the forget's later ``DEL`` (also after its own marker
#: ``SET``) removes it. There is no interleaving in which a superseded revision
#: lands after an erasure.
_WRITE_UNLESS_FORGOTTEN_LUA = """
if redis.call('EXISTS', KEYS[2]) == 1 then
  return 0
end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
return 1
"""

#: Failures a later attempt can fix. A timeout or a dropped connection is the
#: outage a retry is for; ``AuthenticationError`` and ``AuthorizationError``
#: subclass ``ConnectionError``, so the non-retryable tuple is checked first.
_RETRYABLE_REDIS_FAILURES = (
    RedisTimeoutError,
    RedisConnectionError,
    BusyLoadingError,
    TryAgainError,
    MasterDownError,
    ClusterDownError,
)

#: Failures that are a property of the deployment or the command, not an outage:
#: an expired password, a missing permission, and a wrong-type reply cannot
#: succeed on the next attempt no matter how long the caller waits. ``DataError``
#: is a client-side refusal for the same reason.
_NON_RETRYABLE_REDIS_FAILURES = (
    AuthenticationError,
    AuthorizationError,
    DataError,
)


def is_retryable_redis_failure(exc: BaseException) -> bool:
    """Whether a failed Redis command is worth retrying.

    Only a timeout, a connection failure, or a cluster state that says "try
    again" is. A wrong-type or authentication error is recorded immediately with
    its reason: retrying it delays the honest ``failed`` state and cannot change
    the outcome.

    The retryable tuple names the transient ``ResponseError`` subclasses
    (``TryAgainError``, ``MasterDownError``) explicitly. A generic
    ``ResponseError`` — a wrong-type reply, a missing permission — is in neither
    tuple and is therefore not retryable.
    """
    if isinstance(exc, _NON_RETRYABLE_REDIS_FAILURES):
        return False
    return isinstance(exc, (OSError, *_RETRYABLE_REDIS_FAILURES))


class CacheInvalidationError(RuntimeError):
    """A cache eviction that did not complete.

    Raised rather than swallowed: a forgotten memory's cached object still holds
    its content, so an eviction failure is a disclosure the caller has to record,
    not a warning to drop. The caller retries and, on exhaustion, writes the
    receipt the erasure ledger reads.

    ``retryable`` keeps the caller from retrying a refusal that cannot change: an
    authentication, permission, or wrong-type error is a property of the
    deployment, not a transient outage. Only a timeout or a connection failure is
    worth the next attempt.
    """

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class MemoryCacheWriter:
    redis: Redis
    settings: Settings
    _hot_zadd_trim: object | None = field(init=False, repr=False, compare=False, default=None)
    _write_guard: object | None = field(init=False, repr=False, compare=False, default=None)

    def object_key(self, org_id: UUID, memory_id: UUID) -> str:
        return memory_object_key(org_id, memory_id)

    def hot_key(self, org_id: UUID, agent_id: UUID) -> str:
        return memory_hot_key(org_id, agent_id)

    def forgotten_key(self, org_id: UUID, memory_id: UUID) -> str:
        return memory_forgotten_key(org_id, memory_id)

    async def forget_memory(self, *, org_id: UUID, agent_id: UUID, memory_id: UUID) -> None:
        """Evict both cached copies, or raise so the caller can record the gap.

        The forgotten marker is written *before* the object delete. A guarded
        write that runs after the marker is refused; one that ran before it is
        removed by the delete. Both eviction verbs are idempotent — DEL of an
        absent key and ZREM of an absent member are no-ops — so a retry after a
        partial failure is safe and a second forget of the same memory cannot
        corrupt another memory's state.
        """
        try:
            await self.redis.set(
                self.forgotten_key(org_id, memory_id),
                "1",
                ex=MEMORY_FORGOTTEN_TTL_SECONDS,
            )
            await self.redis.delete(self.object_key(org_id, memory_id))
            await self.redis.zrem(self.hot_key(org_id, agent_id), str(memory_id))
        except (OSError, RedisError) as exc:
            WRITE_CACHE_ERRORS.labels(op="forget_invalidate").inc()
            # Fixed message: the caller records this type name in a receipt, and
            # a Redis error can carry the endpoint, never memory content.
            raise CacheInvalidationError(
                f"memory cache eviction failed: {type(exc).__name__}",
                retryable=is_retryable_redis_failure(exc),
            ) from exc

    async def write_created(self, outcome: WriteOutcome) -> None:
        if outcome.kind != WriteOutcomeKind.CREATED:
            return
        memory = outcome.memory
        ttl = self.settings.memory_cache_ttl_seconds
        suppressed = False
        try:
            suppressed = not await self._write_object(memory, ttl)
        except (OSError, RedisError):
            WRITE_CACHE_ERRORS.labels(op="object_cache").inc()
            logger.warning(
                "object cache write failed org_id=%s memory_id=%s",
                memory.org_id,
                memory.id,
            )
        if suppressed:
            # The memory was forgotten after this create committed. The object
            # write is refused and the hot member is not re-added: a ranking
            # entry for a tombstoned memory is stale state the forget removed.
            WRITE_CACHE_ERRORS.labels(op="object_cache_forgotten").inc()
            logger.info(
                "object cache write suppressed: memory was forgotten org_id=%s memory_id=%s",
                memory.org_id,
                memory.id,
            )
            return
        await self.refresh_hot(memory, ttl=ttl)

    async def refresh_hot(
        self,
        memory: MemoryRow,
        *,
        ttl: int | None = None,
    ) -> None:
        """Recompute and ZADD hot score. Fail-open on Redis errors."""
        resolved_ttl = ttl if ttl is not None else self.settings.memory_cache_ttl_seconds
        try:
            await self._write_hot(memory, resolved_ttl)
        except (OSError, RedisError):
            WRITE_CACHE_ERRORS.labels(op="hot_zset").inc()
            logger.warning(
                "hot cache write failed org_id=%s memory_id=%s",
                memory.org_id,
                memory.id,
            )

    async def _write_object(self, memory: MemoryRow, ttl: int) -> bool:
        payload: dict[str, Any] = {
            "id": str(memory.id),
            "content": memory.content,
            "category": memory.category,
            "confidence": memory.confidence,
            "status": memory.status,
            "agent_id": str(memory.agent_id),
            "org_id": str(memory.org_id),
        }
        key = self.object_key(memory.org_id, memory.id)
        return bool(
            await self._guard()(
                keys=[key, self.forgotten_key(memory.org_id, memory.id)],
                args=[json.dumps(payload), ttl],
            )
        )

    def _guard(self) -> Any:
        if self._write_guard is None:
            object.__setattr__(
                self,
                "_write_guard",
                self.redis.register_script(_WRITE_UNLESS_FORGOTTEN_LUA),
            )
        return self._write_guard


    async def _write_hot(self, memory: MemoryRow, ttl: int) -> None:
        if self._hot_zadd_trim is None:
            object.__setattr__(self, "_hot_zadd_trim", register_hot_zadd_trim_script(self.redis))
        score = compute_hot_cache_score(memory, weights=self.settings.rank_weights())
        key = self.hot_key(memory.org_id, memory.agent_id)
        await zadd_hot_memory(
            self._hot_zadd_trim,
            HotZaddRequest(
                key=key,
                memory_id=memory.id,
                score=score,
                ttl_seconds=ttl,
            ),
        )
