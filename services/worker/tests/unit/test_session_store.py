"""Unit tests for org-scoped session pointer helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.extraction.session_store import PostgresSessionStore, SessionSnapshot, _set_org_guc


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


def _session_factory(execute: AsyncMock) -> MagicMock:
    session = MagicMock()
    session.execute = execute
    begin_cm = MagicMock()
    begin_cm.__aenter__ = AsyncMock(return_value=None)
    begin_cm.__aexit__ = AsyncMock(return_value=None)
    session.begin.return_value = begin_cm
    factory = MagicMock()
    factory_cm = MagicMock()
    factory_cm.__aenter__ = AsyncMock(return_value=session)
    factory_cm.__aexit__ = AsyncMock(return_value=None)
    factory.return_value = factory_cm
    return factory


@pytest.mark.asyncio
async def test_load_found_binds_org_and_session() -> None:
    org_id, session_id = uuid4(), uuid4()
    row = SimpleNamespace(last_extracted_turn=4, status="completed", deleted_at=None)
    result = MagicMock()
    result.one_or_none.return_value = row
    execute = AsyncMock(return_value=result)
    store = PostgresSessionStore(_session_factory(execute))
    snap = await store._load(org_id, session_id)
    assert snap == SessionSnapshot(4, "completed", None)
    assert execute.await_count == 2
    select_params = execute.await_args_list[1].args[1]
    assert select_params["org_id"] == org_id
    assert select_params["session_id"] == session_id


@pytest.mark.asyncio
async def test_load_none_when_missing() -> None:
    result = MagicMock()
    result.one_or_none.return_value = None
    execute = AsyncMock(return_value=result)
    store = PostgresSessionStore(_session_factory(execute))
    assert await store._load(uuid4(), uuid4()) is None


@pytest.mark.asyncio
async def test_update_binds_turn_and_org() -> None:
    org_id, session_id = uuid4(), uuid4()
    execute = AsyncMock()
    store = PostgresSessionStore(_session_factory(execute))
    await store._update(org_id, session_id, 11)
    assert execute.await_count == 2
    update_params = execute.await_args_list[1].args[1]
    assert update_params == {
        "turn": 11,
        "session_id": session_id,
        "org_id": org_id,
    }
    update_sql = execute.await_args_list[1].args[0].text
    assert "GREATEST(last_extracted_turn" in update_sql
