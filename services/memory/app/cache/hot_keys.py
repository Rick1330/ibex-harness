"""Redis key helpers for per-agent hot memory sorted sets (m3.D.3)."""

from __future__ import annotations

from uuid import UUID

HOT_CACHE_CAPACITY = 50


def hot_memories_key(org_id: UUID, agent_id: UUID) -> str:
    return f"org_id:{org_id}:hot_memories:{agent_id}"
