"""Unit tests for budget Redis publish helpers (4.P.4)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.budget_publish import (
    NoopBudgetPublisher,
    RecordingBudgetPublisher,
    RedisBudgetPublisher,
)


@pytest.mark.asyncio
async def test_noop_and_recording_publishers() -> None:
    await NoopBudgetPublisher().publish_budget_update("org-1")
    rec = RecordingBudgetPublisher()
    await rec.publish_budget_update("org-2")
    assert rec.published == ["org-2"]


@pytest.mark.asyncio
async def test_redis_budget_publisher_publish_and_aclose(monkeypatch: Any) -> None:
    published: list[tuple[str, str]] = []

    class FakeRedis:
        async def publish(self, channel: str, payload: str) -> int:
            published.append((channel, payload))
            return 1

        async def aclose(self) -> None:
            return None

    fake = FakeRedis()
    monkeypatch.setattr(
        "app.budget_publish._redis_from_url",
        lambda url: fake,
    )
    pub = RedisBudgetPublisher("redis://localhost:6379/0")
    await pub.publish_budget_update("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    assert published[0][0].startswith("budget_updates:")
    assert "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in published[0][1]
    await pub.aclose()
    # second aclose is a no-op
    await pub.aclose()


@pytest.mark.asyncio
async def test_redis_budget_publisher_lazy_client(monkeypatch: Any) -> None:
    client = MagicMock()
    client.publish = AsyncMock(return_value=1)
    client.aclose = AsyncMock()
    monkeypatch.setattr("app.budget_publish._redis_from_url", lambda url: client)
    pub = RedisBudgetPublisher("redis://x")
    await pub.publish_budget_update("org")
    await pub.publish_budget_update("org")
    assert client.publish.await_count == 2
    await pub.aclose()
    client.aclose.assert_awaited_once()
