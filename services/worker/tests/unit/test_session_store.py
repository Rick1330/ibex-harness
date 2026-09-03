"""Unit tests for org-scoped session pointer helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.extraction.session_store import PostgresSessionStore, _set_org_guc


@pytest.mark.asyncio
async def test_set_org_guc_binds_org_id() -> None:
    session = AsyncMock()
    org_id = uuid4()
    await _set_org_guc(session, org_id)
    bound = session.execute.await_args.args[1]
    assert bound["org_id"] == str(org_id)


def test_postgres_store_load_and_update_delegate(monkeypatch: pytest.MonkeyPatch) -> None:
    store = PostgresSessionStore(MagicMock())
    org_id, session_id = uuid4(), uuid4()

    async def fake_load(_org, _sid):
        from app.extraction.session_store import SessionSnapshot

        return SessionSnapshot(last_extracted_turn=2, status="completed", deleted_at=None)

    async def fake_update(_org, _sid, turn: int) -> None:
        fake_update.turn = turn  # type: ignore[attr-defined]

    monkeypatch.setattr(store, "_load", fake_load)
    monkeypatch.setattr(store, "_update", fake_update)
    snap = store.load(org_id, session_id)
    assert snap is not None
    assert snap.last_extracted_turn == 2
    store.update_last_extracted_turn(org_id, session_id, 9)
    assert fake_update.turn == 9  # type: ignore[attr-defined]
