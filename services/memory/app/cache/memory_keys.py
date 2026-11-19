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
"""

from __future__ import annotations

from uuid import UUID

from app.cache.hot_keys import hot_memories_key

#: Store names the cache receipts and refs use. They are part of the database
#: contract (000078 CHECK constraints) and of the erasure response schema.
OBJECT_CACHE_STORE = "cache"
HOT_CACHE_STORE = "cache_hot"


def memory_object_key(org_id: UUID, memory_id: UUID) -> str:
    """Key of the cached memory object: the copy that carries content."""
    return f"{org_id}:memory:{memory_id}"


def memory_hot_key(org_id: UUID, agent_id: UUID) -> str:
    """Key of the per-agent hot sorted set the memory id is a member of."""
    return hot_memories_key(org_id, agent_id)
