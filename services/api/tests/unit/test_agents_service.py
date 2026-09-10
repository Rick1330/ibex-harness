"""Unit tests for agent service lifecycle and list helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from apierror_py import (
    AGENT_HAS_SESSIONS,
    AGENT_SLUG_CONFLICT,
    AGENT_STATUS_CONFLICT,
    NOT_FOUND,
    VALIDATION_ERROR,
)
from sqlalchemy.exc import IntegrityError

from app.errors import ApiError
from app.pagination import encode_cursor
from app.schemas.agents import AgentCreate, AgentPatch
from app.services import agents as agent_service
from app.services.agents import (
    AgentListFilters,
    CreateAgentArgs,
    ListAgentsArgs,
    _assert_lifecycle_transition,
)


class _MapResult:
    def __init__(self, row, *, scalar=None):
        self._row = row
        self._scalar = scalar

    def mappings(self):
        return self

    def first(self):
        return self._row

    def all(self):
        return [self._row] if self._row is not None else []

    def scalar(self):
        return self._scalar


def _agent_row(**overrides):
    now = datetime.now(UTC)
    org_id = overrides.pop("org_id", uuid4())
    base = {
        "id": overrides.pop("id", uuid4()),
        "org_id": org_id,
        "slug": "support",
        "name": "Support",
        "description": None,
        "status": "active",
        "default_provider": None,
        "default_model": None,
        "active_directive_version_id": None,
        "config": {},
        "metadata": {},
        "tags": ["prod"],
        "total_sessions": 0,
        "total_memories": 0,
        "total_tokens_used": 0,
        "last_active_at": None,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _integrity(constraint: str) -> IntegrityError:
    class _Orig:
        constraint_name = constraint

    return IntegrityError("stmt", {}, _Orig())


async def _expect_code(awaitable, code: str) -> None:
    with pytest.raises(ApiError) as exc:
        await awaitable
    assert exc.value.code == code


@pytest.mark.asyncio
async def test_get_agent_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_MapResult(None))
    await _expect_code(agent_service.get_agent(session, uuid4(), uuid4()), NOT_FOUND)


@pytest.mark.asyncio
async def test_get_agent_with_directive() -> None:
    directive_id = uuid4()
    row = _agent_row(active_directive_version_id=directive_id)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_MapResult(row))
    out = await agent_service.get_agent(session, row.org_id, row.id)
    assert out.active_directive_version_id == directive_id


@pytest.mark.asyncio
async def test_create_slug_conflict() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_integrity("agents_org_id_slug_key"))
    session.rollback = AsyncMock()
    args = CreateAgentArgs(org_id=uuid4(), body=AgentCreate(name="A", slug="dup"), created_by=None)
    await _expect_code(agent_service.create_agent(session, args), AGENT_SLUG_CONFLICT)


@pytest.mark.asyncio
async def test_create_other_integrity_is_validation() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_integrity("agents_description_max"))
    session.rollback = AsyncMock()
    args = CreateAgentArgs(org_id=uuid4(), body=AgentCreate(name="A", slug="a"), created_by=None)
    await _expect_code(agent_service.create_agent(session, args), VALIDATION_ERROR)


@pytest.mark.asyncio
async def test_create_agent_ok() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    created_row = _agent_row(id=agent_id, org_id=org_id)
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[_MapResult({"id": agent_id}), _MapResult(created_row)]
    )
    session.commit = AsyncMock()
    out = await agent_service.create_agent(
        session,
        CreateAgentArgs(
            org_id=org_id,
            body=AgentCreate(name="Support", slug="support", default_provider="openai"),
            created_by=uuid4(),
        ),
    )
    assert out.id == agent_id
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_soft_delete_blocked_with_sessions() -> None:
    row = {"id": uuid4(), "total_sessions": 0}
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_MapResult(row), _MapResult(None, scalar=True)])
    await _expect_code(
        agent_service.soft_delete_agent(session, uuid4(), row["id"]), AGENT_HAS_SESSIONS
    )


@pytest.mark.asyncio
async def test_soft_delete_blocked_with_counter() -> None:
    row = {"id": uuid4(), "total_sessions": 3}
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_MapResult(row), _MapResult(None, scalar=False)])
    await _expect_code(
        agent_service.soft_delete_agent(session, uuid4(), row["id"]), AGENT_HAS_SESSIONS
    )


@pytest.mark.asyncio
async def test_soft_delete_ok() -> None:
    agent_id = uuid4()
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _MapResult({"id": agent_id, "total_sessions": 0}),
            _MapResult(None, scalar=False),
            _MapResult({"id": agent_id}),
        ]
    )
    session.commit = AsyncMock()
    await agent_service.soft_delete_agent(session, uuid4(), agent_id)
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_soft_delete_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_MapResult(None))
    await _expect_code(agent_service.soft_delete_agent(session, uuid4(), uuid4()), NOT_FOUND)


@pytest.mark.parametrize(
    ("current", "action", "want"),
    [
        ("active", "pause", "paused"),
        ("paused", "activate", "active"),
        ("archived", "activate", "active"),
        ("suspended", "activate", "active"),
        ("active", "archive", "archived"),
        ("paused", "archive", "archived"),
    ],
)
def test_lifecycle_allowed(current: str, action: str, want: str) -> None:
    assert _assert_lifecycle_transition(current, action) == want  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("current", "action"),
    [
        ("paused", "pause"),
        ("active", "activate"),
        ("archived", "archive"),
        ("suspended", "pause"),
    ],
)
def test_lifecycle_illegal(current: str, action: str) -> None:
    with pytest.raises(ApiError) as exc:
        _assert_lifecycle_transition(current, action)  # type: ignore[arg-type]
    assert exc.value.code == VALIDATION_ERROR


@pytest.mark.asyncio
async def test_pause_agent() -> None:
    row = _agent_row(status="active")
    paused = _agent_row(id=row.id, org_id=row.org_id, status="paused")
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[_MapResult(row), _MapResult({"id": row.id}), _MapResult(paused)]
    )
    session.commit = AsyncMock()
    out = await agent_service.pause_agent(session, row.org_id, row.id)
    assert out.status == "paused"


@pytest.mark.asyncio
async def test_pause_cas_conflict() -> None:
    row = _agent_row(status="active")
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_MapResult(row), _MapResult(None)])
    await _expect_code(agent_service.pause_agent(session, row.org_id, row.id), AGENT_STATUS_CONFLICT)


@pytest.mark.asyncio
async def test_list_agents_filters_and_cursor() -> None:
    org_id = uuid4()
    now = datetime.now(UTC)
    row = _agent_row(org_id=org_id, created_at=now)
    row2 = _agent_row(org_id=org_id, created_at=now, id=uuid4(), slug="other")

    class _Multi:
        def mappings(self):
            return self

        def all(self):
            return [row, row2]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Multi())
    page = await agent_service.list_agents(
        session,
        ListAgentsArgs(
            org_id=org_id,
            cursor=None,
            limit=1,
            filters=AgentListFilters(status="active", tags=["prod"], search="sup"),
        ),
    )
    assert len(page.data) == 1
    assert page.pagination.has_more is True

    session.execute = AsyncMock(return_value=_Multi())
    page2 = await agent_service.list_agents(
        session,
        ListAgentsArgs(
            org_id=org_id,
            cursor=page.pagination.next_cursor,
            limit=10,
            filters=AgentListFilters(),
        ),
    )
    assert len(page2.data) == 2
    assert page2.pagination.has_more is False


@pytest.mark.asyncio
async def test_list_invalid_cursor() -> None:
    session = AsyncMock()
    args = ListAgentsArgs(org_id=uuid4(), cursor="!!!", limit=10, filters=AgentListFilters())
    await _expect_code(agent_service.list_agents(session, args), VALIDATION_ERROR)


@pytest.mark.asyncio
async def test_list_cursor_missing_fields() -> None:
    session = AsyncMock()
    args = ListAgentsArgs(
        org_id=uuid4(),
        cursor=encode_cursor({"created_at": "x"}),
        limit=10,
        filters=AgentListFilters(),
    )
    await _expect_code(agent_service.list_agents(session, args), VALIDATION_ERROR)


@pytest.mark.asyncio
async def test_patch_agent() -> None:
    row = _agent_row()
    updated = _agent_row(id=row.id, org_id=row.org_id, name="Renamed", default_provider="openai")
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[_MapResult({"id": row.id}), _MapResult(updated)]
    )
    session.commit = AsyncMock()
    patch = AgentPatch(name="Renamed", default_provider="openai", default_model="gpt-4o")
    out = await agent_service.patch_agent(session, row.org_id, row.id, patch)
    assert out.name == "Renamed"


@pytest.mark.asyncio
async def test_patch_noop_returns_current() -> None:
    row = _agent_row()
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_MapResult(row)])
    out = await agent_service.patch_agent(session, row.org_id, row.id, AgentPatch())
    assert out.id == row.id


@pytest.mark.asyncio
async def test_patch_not_found_on_update() -> None:
    row = _agent_row()
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_MapResult(None)])
    patch = AgentPatch(name="Renamed")
    await _expect_code(
        agent_service.patch_agent(session, row.org_id, row.id, patch), NOT_FOUND
    )


@pytest.mark.asyncio
async def test_activate_and_archive() -> None:
    paused = _agent_row(status="paused")
    active = _agent_row(id=paused.id, org_id=paused.org_id, status="active")
    archived = _agent_row(id=paused.id, org_id=paused.org_id, status="archived")
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _MapResult(paused),
            _MapResult({"id": paused.id}),
            _MapResult(active),
            _MapResult(active),
            _MapResult({"id": paused.id}),
            _MapResult(archived),
        ]
    )
    session.commit = AsyncMock()
    assert (await agent_service.activate_agent(session, paused.org_id, paused.id)).status == "active"
    assert (await agent_service.archive_agent(session, paused.org_id, paused.id)).status == "archived"


@pytest.mark.asyncio
async def test_create_integrity_diag_constraint() -> None:
    class _Diag:
        constraint_name = "agents_org_id_slug_key"

    class _Orig:
        diag = _Diag()

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=IntegrityError("stmt", {}, _Orig()))
    session.rollback = AsyncMock()
    args = CreateAgentArgs(org_id=uuid4(), body=AgentCreate(name="A", slug="dup"), created_by=None)
    await _expect_code(agent_service.create_agent(session, args), AGENT_SLUG_CONFLICT)


@pytest.mark.asyncio
async def test_soft_delete_race_after_lock() -> None:
    agent_id = uuid4()
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _MapResult({"id": agent_id, "total_sessions": 0}),
            _MapResult(None, scalar=False),
            _MapResult(None),
        ]
    )
    await _expect_code(agent_service.soft_delete_agent(session, uuid4(), agent_id), NOT_FOUND)


@pytest.mark.asyncio
async def test_create_unable_when_returning_empty() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_MapResult(None))
    args = CreateAgentArgs(org_id=uuid4(), body=AgentCreate(name="A", slug="a"), created_by=None)
    await _expect_code(agent_service.create_agent(session, args), VALIDATION_ERROR)


def test_agent_from_row_tags_tuple() -> None:
    assert agent_service._agent_from_row(_agent_row(tags=("a", "b"))).tags == ["a", "b"]


def test_row_get_getattr_fallback() -> None:
    class AttrOnly:
        def __init__(self) -> None:
            self.id = uuid4()

    obj = AttrOnly()
    assert agent_service._row_get(obj, "id") == obj.id


def test_sessions_block_delete_helper() -> None:
    assert agent_service._sessions_block_delete(live_sessions=True, total_sessions=0) is True
    assert agent_service._sessions_block_delete(live_sessions=False, total_sessions=2) is True
    assert agent_service._sessions_block_delete(live_sessions=False, total_sessions=0) is False
