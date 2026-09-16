"""Capture redaction task unit tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.tasks import capture_redaction


@pytest.mark.asyncio
async def test_resolve_capture_mode_defaults_metadata_only() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=None)))
    mode = await capture_redaction.resolve_capture_mode(session, org_id="o", agent_id=None)
    assert mode == "metadata_only"


@pytest.mark.asyncio
async def test_resolve_capture_mode_uses_row() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=("full",))))
    mode = await capture_redaction.resolve_capture_mode(session, org_id="o", agent_id=None)
    assert mode == "full"


def test_task_limits() -> None:
    assert capture_redaction.apply_capture_redaction.soft_time_limit == 120
    assert capture_redaction.apply_capture_redaction.time_limit == 180
