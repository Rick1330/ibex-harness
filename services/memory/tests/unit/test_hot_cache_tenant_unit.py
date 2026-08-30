"""Cross-tenant hot cache key isolation unit tests (m3.D.3)."""

from __future__ import annotations

from uuid import uuid4

from app.cache.hot_keys import hot_memories_key


def test_same_agent_different_orgs_get_different_keys() -> None:
    agent_id = uuid4()
    org_a = uuid4()
    org_b = uuid4()
    assert hot_memories_key(org_a, agent_id) != hot_memories_key(org_b, agent_id)


def test_same_org_different_agents_get_different_keys() -> None:
    org_id = uuid4()
    agent_a = uuid4()
    agent_b = uuid4()
    assert hot_memories_key(org_id, agent_a) != hot_memories_key(org_id, agent_b)
