"""Unit tests for the metadata-only operator session read service."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from apierror_py import NOT_FOUND, VALIDATION_ERROR

from app.errors import ApiError
from app.pagination import decode_cursor, encode_cursor
from app.services import operator_sessions as session_service
from app.services.operator_keyset import keyset_cursor_payload
from app.services.operator_sessions import ListSessionsArgs, SessionListFilters
from tests.unit.operator.session_fixtures import (
    NOW,
    evidence_record,
    session_row,
    turn_row,
)


class _MapResult:
    def __init__(self, rows: list[object] | None = None) -> None:
        self._rows = rows or []

    def mappings(self) -> _MapResult:
        return self

    def first(self) -> object | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[object]:
        return list(self._rows)


def _session(*results: list[object]) -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_MapResult(rows) for rows in results])
    return session


def _args(**overrides: object) -> ListSessionsArgs:
    data: dict[str, object] = {
        "org_id": uuid4(),
        "cursor": None,
        "limit": 50,
        "filters": SessionListFilters(),
    }
    data.update(overrides)
    return ListSessionsArgs(**data)  # type: ignore[arg-type]


async def _expect_code(awaitable: object, code: str) -> ApiError:
    with pytest.raises(ApiError) as exc:
        await awaitable  # type: ignore[misc]
    assert exc.value.code == code
    return exc.value


@pytest.mark.asyncio
async def test_get_session_returns_not_found_without_reading_turns() -> None:
    session = _session([])
    org_id = uuid4()
    session_id = uuid4()

    error = await _expect_code(
        session_service.get_operator_session(session, org_id, session_id), NOT_FOUND
    )

    assert error.message == "Session not found"
    assert session.execute.await_count == 1
    statement, params = session.execute.call_args.args
    assert "ibex_core.sessions" in str(statement)
    assert "deleted_at IS NULL" in str(statement)
    assert params == {"org_id": org_id, "session_id": session_id}


@pytest.mark.asyncio
async def test_get_session_projects_turns_and_links_trace() -> None:
    session_id = uuid4()
    row = session_row(id=session_id)
    evidence = evidence_record()
    traced = turn_row(trace=evidence, turn_index=0)
    untraced = turn_row(turn_index=1, request_id="req-2")
    session = _session([row], [traced, untraced])

    detail = await session_service.get_operator_session(session, uuid4(), session_id)

    assert detail.id == session_id
    assert detail.turn_count == 2
    assert detail.turns_truncated is False
    assert [turn.turn_index for turn in detail.turns] == [0, 1]
    assert detail.turns[0].trace is not None
    assert detail.turns[0].trace.trace_id == evidence.trace_id
    assert detail.turns[0].trace.run_id == evidence.run_id
    assert detail.turns[1].trace is None
    dumped = detail.model_dump()
    assert "messages_hash" not in dumped
    assert "org_id" not in dumped


@pytest.mark.asyncio
async def test_get_session_normalizes_non_ok_evidence_status() -> None:
    evidence = evidence_record(status="error", error_code="provider_timeout")
    session = _session([session_row()], [turn_row(trace=evidence)])

    detail = await session_service.get_operator_session(session, uuid4(), uuid4())

    assert detail.turns[0].trace is not None
    assert detail.turns[0].trace.status == "error"
    assert detail.turns[0].trace.error_code == "provider_timeout"


@pytest.mark.asyncio
async def test_get_session_marks_and_slices_truncated_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_service, "MAX_SESSION_TURNS", 2)
    turns = [turn_row(turn_index=index) for index in range(3)]
    session = _session([session_row()], turns)

    detail = await session_service.get_operator_session(session, uuid4(), uuid4())

    assert len(detail.turns) == 2
    assert detail.turns_truncated is True


@pytest.mark.asyncio
async def test_list_sessions_forwards_filters_and_builds_the_next_cursor() -> None:
    first, second = session_row(), session_row()
    session = _session([first, second])
    args = _args(
        limit=1,
        filters=SessionListFilters(agent_id=uuid4(), status="completed"),
    )

    page = await session_service.list_operator_sessions(session, args)

    assert [item.id for item in page.data] == [first.id]
    assert page.pagination.has_more is True
    assert page.pagination.next_cursor is not None
    assert decode_cursor(page.pagination.next_cursor) == {
        "created_at": first.created_at.isoformat(),
        "id": str(first.id),
    }
    params = session.execute.call_args.args[1]
    assert params["org_id"] == args.org_id
    assert params["limit"] == 2
    assert params["agent_id"] == args.filters.agent_id
    assert params["status"] == "completed"
    assert "cursor_created_at" not in params


@pytest.mark.asyncio
async def test_list_sessions_excludes_deleted_rows_in_the_statement() -> None:
    row = session_row()
    args = _args(limit=50)
    session = _session([row])

    page = await session_service.list_operator_sessions(session, args)

    assert page.pagination.has_more is False
    statement = str(session.execute.call_args.args[0])
    assert "deleted_at IS NULL" in statement
    assert "ORDER BY ibex_core.sessions.created_at DESC" in statement



@pytest.mark.asyncio
async def test_list_sessions_applies_a_valid_cursor() -> None:
    row = session_row()
    row_id = uuid4()
    cursor = encode_cursor(keyset_cursor_payload(NOW, row_id))
    session = _session([row])

    await session_service.list_operator_sessions(session, _args(cursor=cursor))

    statement, params = session.execute.call_args.args
    assert params["cursor_created_at"] == NOW
    assert params["cursor_id"] == row_id
    assert "created_at <" in str(statement)


@pytest.mark.asyncio
async def test_list_sessions_rejects_an_invalid_cursor_before_querying() -> None:
    session = _session([])

    await _expect_code(
        session_service.list_operator_sessions(session, _args(cursor="not+base64")),
        VALIDATION_ERROR,
    )
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_sessions_accepts_dict_rows() -> None:
    row = session_row()
    session = _session([row.__dict__])

    page = await session_service.list_operator_sessions(session, _args())

    assert page.data[0].id == row.id

