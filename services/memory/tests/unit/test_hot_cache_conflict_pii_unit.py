"""Hot-cache drop order: a PII-blocked conflict winner must not erase the pair.

The search paths were changed to run the Tier-1 PII re-check *before* the
conflict collapse for exactly this reason: if the blocked row suppresses its
counterpart first and is then dropped itself, two recoverable hits become an
empty page. The hot-cache page runs the same guard and the same collapse, so it
needs the same order.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.read.hot_cache import MemoryHotCacheReader
from app.read.models import HotMemoryQuery


def _row(memory_id: UUID, org_id: UUID, agent_id: UUID, *, content: str) -> dict:
    now = datetime.now(tz=UTC)
    return {
        "id": memory_id,
        "org_id": org_id,
        "agent_id": agent_id,
        "content": content,
        "category": "factual",
        "confidence": 0.9,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }


def _reader(rows: list[dict], zset: list[tuple[UUID, float]]) -> MemoryHotCacheReader:
    redis = AsyncMock()
    redis.zrevrange = AsyncMock(
        return_value=[
            (str(memory_id).encode(), score) for memory_id, score in zset
        ]
    )
    session = MagicMock()
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    begin = MagicMock()
    begin.__aenter__ = AsyncMock(return_value=session)
    begin.__aexit__ = AsyncMock(return_value=None)
    session.begin = MagicMock(return_value=begin)
    factory = MagicMock(
        return_value=MagicMock(
            __aenter__=AsyncMock(return_value=session),
            __aexit__=AsyncMock(return_value=None),
        )
    )
    return MemoryHotCacheReader(redis, factory)


@pytest.mark.asyncio
async def test_pii_blocked_winner_leaves_the_other_side_visible() -> None:
    org_id, agent_id = uuid4(), uuid4()
    winner, loser = uuid4(), uuid4()
    group = str(uuid4())
    reader = _reader(
        [
            {
                **_row(
                    winner,
                    org_id,
                    agent_id,
                    content="reach me at someone@example.com",
                ),
                "conflict_groups": [group],
            },
            {
                **_row(loser, org_id, agent_id, content="plain claim"),
                "conflict_groups": [group],
            },
        ],
        [(winner, 0.9), (loser, 0.7)],
    )

    results = await reader.get_hot_memories(
        HotMemoryQuery(org_id=org_id, agent_id=agent_id, limit=10)
    )

    assert [item.id for item in results] == [loser]
