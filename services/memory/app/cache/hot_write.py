"""Atomic hot sorted-set write (ZADD + trim + TTL) for m3.D.3."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from redis.asyncio import Redis

# Keep top HOT_CACHE_CAPACITY members; trim lowest ranks when count exceeds capacity.
#
# KEYS[2] is the memory's forgotten marker, and the check and the write are one
# script for the same reason the object write is: a create that committed before
# its after-commit hot write can run after a forget has set the marker and removed
# the member. A read followed by a separate ZADD would let that write re-add the
# member after the erasure verified it absent. Redis runs a script atomically, so
# either the marker exists and nothing is written (returns 0), or the write lands
# and the forget's ZREM (which follows its own marker SET) removes it.
_HOT_ZADD_TRIM_LUA = """
if redis.call('EXISTS', KEYS[2]) == 1 then
  return 0
end
redis.call('ZADD', KEYS[1], ARGV[1], ARGV[2])
redis.call('ZREMRANGEBYRANK', KEYS[1], 0, -51)
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
return redis.call('ZCARD', KEYS[1])
"""


def register_hot_zadd_trim_script(redis: Redis):
    return redis.register_script(_HOT_ZADD_TRIM_LUA)


@dataclass(frozen=True, slots=True)
class HotZaddRequest:
    key: str
    forgotten_key: str
    memory_id: UUID
    score: float
    ttl_seconds: int


async def zadd_hot_memory(script, request: HotZaddRequest) -> int:
    """Atomically ZADD, trim to top 50, refresh TTL. Returns ZCARD after write.

    A return of 0 means the forgotten marker was present and the member was not
    written; a real write always leaves at least one member, so the two cases do
    not collide.
    """
    result = await script(
        keys=[request.key, request.forgotten_key],
        args=[request.score, str(request.memory_id), request.ttl_seconds],
    )
    return int(result)
