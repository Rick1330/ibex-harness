"""Redis addresses of a memory's cached copies, defined once.

Two structures hold a copy of a memory after a write:

* the object cache entry ``{org_id}:memory:{memory_id}`` — a JSON string whose
  ``content`` field is the memory's text, TTL ``memory_cache_ttl_seconds``;
* the per-agent hot sorted set ``{org_id}:hot_memories:{agent_id}`` — membership
  plus a ranking score, no content.

The write path, the forget path and the erasure consumer must address the same
two keys, so the format lives here rather than in three f-strings. The consumer
receives the keys as ``memory_artifact_refs`` locators, so it never imports this
module: a change here reaches it through the ref the forget transaction writes.

The third key, ``{org_id}:memory_forgotten:{memory_id}``, is not a copy: it is
the marker that stops a write already in flight from recreating a copy after a
forget deleted it. It carries no content and expires.
"""

from __future__ import annotations

from uuid import UUID

from app.cache.hot_keys import hot_memories_key

#: Store names the cache receipts and refs use. They are part of the database
#: contract (000078 CHECK constraints) and of the erasure response schema.
OBJECT_CACHE_STORE = "cache"
HOT_CACHE_STORE = "cache_hot"

#: Namespace of the erased-memory marker. It is deliberately not a store in the
#: erasure ledger: it holds no content, and it exists only to make a delayed
#: after-commit object write lose to a forget that already ran. Without it, a
#: create that committed before ``AfterCommitHandler.write_created`` could SET
#: the object key back *after* the forget (or the worker) deleted it — a
#: time-of-check/time-of-use hole in the erasure guarantee, not merely stale
#: cache state.
MEMORY_FORGOTTEN_NAMESPACE = "memory_forgotten"

#: Marker lifetime. It must outlive any write that was already in flight when
#: the forget committed: a request lives for seconds, so a week is generous. The
#: marker holds the memory id and nothing else, and it expires, so the set stays
#: bounded and content-free.
MEMORY_FORGOTTEN_TTL_SECONDS = 7 * 24 * 60 * 60


def memory_object_key(org_id: UUID, memory_id: UUID) -> str:
    """Key of the cached memory object: the copy that carries content."""
    return f"{org_id}:memory:{memory_id}"


def memory_hot_key(org_id: UUID, agent_id: UUID) -> str:
    """Key of the per-agent hot sorted set the memory id is a member of."""
    return hot_memories_key(org_id, agent_id)


def memory_forgotten_key(org_id: UUID, memory_id: UUID) -> str:
    """Marker that fences a delayed write for ``memory_id`` out of the cache."""
    return f"{org_id}:{MEMORY_FORGOTTEN_NAMESPACE}:{memory_id}"
