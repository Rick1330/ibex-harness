"""Unit tests for org deletion cascade task helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.tasks import org_deletion


@pytest.mark.asyncio
async def test_claim_job_returns_false_when_missing() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=None)))
    claimed = await org_deletion._claim_job(session, job_id="j", org_id="o")
    assert claimed is False


@pytest.mark.asyncio
async def test_run_delete_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = MagicMock(database_url=None)
    monkeypatch.setattr(org_deletion, "get_settings", lambda: settings)
    with pytest.raises(ValueError, match="database_url"):
        await org_deletion._run_delete(job_id="j", org_id="o")


@pytest.mark.asyncio
async def test_run_delete_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = MagicMock(database_url="postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setattr(org_deletion, "get_settings", lambda: settings)

    engine = MagicMock()
    engine.dispose = AsyncMock()
    monkeypatch.setattr(org_deletion, "create_engine", lambda _s: engine)
    monkeypatch.setattr(org_deletion, "create_session_factory", lambda _e: MagicMock())

    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            MagicMock(first=MagicMock(return_value=(1,))),  # claim
            *([MagicMock()] * len(org_deletion._CASCADE_STATEMENTS)),
            MagicMock(),  # finish
        ]
    )

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(org_deletion, "session_as_service_account", lambda _f: _CM())
    out = await org_deletion._run_delete(job_id="j", org_id="o")
    assert out["status"] == "succeeded"


def test_cascade_includes_soft_delete_org() -> None:
    joined = "\n".join(org_deletion._CASCADE_STATEMENTS)
    assert "deleted_at" in joined
    assert "memory_feedback" in joined
    assert "organization_invites" in joined
    assert "session_turns" not in joined
