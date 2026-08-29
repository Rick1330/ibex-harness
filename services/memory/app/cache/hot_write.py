"""Atomic hot sorted-set write (ZADD + trim + TTL) for m3.D.3."""

from __future__ import annotations

from uuid import UUID

from redis.asyncio import Redis

# Keep top HOT_CACHE_CAPACITY members; trim lowest ranks when count exceeds capacity.
_HOT_ZADD_TRIM_LUA = """
redis.call('ZADD', KEYS[1], ARGV[1], ARGV[2])
redis.call('ZREMRANGEBYRANK', KEYS[1], 0, -51)
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
return redis.call('ZCARD', KEYS[1])
"""


def register_hot_zadd_trim_script(redis: Redis):
    return redis.register_script(_HOT_ZADD_TRIM_LUA)


async def zadd_hot_memory(
    script,
    *,
    key: str,
    memory_id: UUID,
    score: float,
    ttl_seconds: int,
) -> int:
    """Atomically ZADD, trim to top 50, refresh TTL. Returns ZCARD after write."""
    result = await script(keys=[key], args=[score, str(memory_id), ttl_seconds])
    return int(result)
