"""Unit tests for write factory wiring."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.config import Settings
from app.write.factory import (
    build_embedding_callable,
    build_write_orchestrator,
    build_write_pipeline,
)
from app.write.pipeline_deps import WritePipelineDeps


@pytest.mark.asyncio
async def test_build_embedding_callable() -> None:
    client = AsyncMock()
    vec = [0.1, 0.2]
    result = MagicMock()
    result.vectors = [vec]
    client.embed = AsyncMock(return_value=result)

    from app.write.embed_context import reset_write_org_id, set_write_org_id

    org = uuid4()
    token = set_write_org_id(org)
    try:
        embed = build_embedding_callable(client)
        got = await embed("hello")
        assert got == vec
        client.embed.assert_awaited_once_with(["hello"], org_id=org)
    finally:
        reset_write_org_id(token)


def test_build_write_pipeline_and_orchestrator() -> None:
    settings = Settings(embedding_api_token="tok")
    session_factory = MagicMock()
    store = MagicMock()
    pii = MagicMock()
    embed = AsyncMock()

    with patch(
        "app.write.factory.find_active_by_content_hash",
        AsyncMock(return_value=None),
    ), patch(
        "app.write.factory.increment_retrieval_count",
        AsyncMock(return_value=1),
    ), patch(
        "app.write.factory.load_candidate_memories",
        AsyncMock(return_value=[]),
    ):
        pipeline = build_write_pipeline(
            WritePipelineDeps(
                settings=settings,
                session_factory=session_factory,
                store=store,
                pii=pii,
                embed=embed,
            )
        )
        assert len(pipeline._stages) == 6

        orch = build_write_orchestrator(
            WritePipelineDeps(
                settings=settings,
                session_factory=session_factory,
                store=store,
                pii=pii,
                embed=embed,
            )
        )
        assert orch is not None
