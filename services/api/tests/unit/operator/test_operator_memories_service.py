"""Unit tests for the metadata-only operator memory read service."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from apierror_py import NOT_FOUND

from app.errors import ApiError
from app.pagination import decode_cursor, encode_cursor
from app.services import operator_memories as memory_service
from app.services.operator_memories import ListMemoriesArgs, MemoryListFilters
from tests.unit.operator.memory_fixtures import NOW, memory_row


class _MapResult:
    def __init__(self, rows: list[object] | None = None, scalar: object = None) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def mappings(self) -> _MapResult:
        return self

    def first(self) -> object | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[object]:
        return list(self._rows)

    def scalar_one_or_none(self) -> object:
        return self._scalar


def _session(rows: list[object], *extra: _MapResult) -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[_MapResult(rows), *(extra or (_MapResult(), _MapResult(), _MapResult()))]
    )
    return session


def _args(**overrides: object) -> ListMemoriesArgs:
    data: dict[str, object] = {
        "org_id": uuid4(),
        "cursor": None,
        "limit": 50,
        "filters": MemoryListFilters(),
    }
    data.update(overrides)
    return ListMemoriesArgs(**data)  # type: ignore[arg-type]


async def _expect_code(awaitable: object, code: str) -> ApiError:
    with pytest.raises(ApiError) as exc:
        await awaitable  # type: ignore[misc]
    assert exc.value.code == code
    return exc.value


@pytest.mark.asyncio
async def test_get_memory_returns_not_found_and_scopes_the_query() -> None:
    session = _session([])
    org_id = uuid4()
    memory_id = uuid4()

    error = await _expect_code(
        memory_service.get_operator_memory(session, org_id, memory_id), NOT_FOUND
    )

    assert error.message == "Memory not found"
    statement, params = session.execute.call_args.args[0], session.execute.call_args.args[1]
    assert "ibex_core.memories" in str(statement)
    assert "org_id" in str(statement)
    assert params == {"org_id": org_id, "memory_id": memory_id}


@pytest.mark.asyncio
async def test_get_memory_projects_metadata_and_parses_tags() -> None:
    row = memory_row(
        tags='["support","billing"]',
        pii_detected=True,
        pii_redacted=True,
        confidence="0.90",
        content_tokens="21",
    )
    replacement = uuid4()
    session = _session(
        [row],
        _MapResult(scalar=str(replacement)),
        _MapResult(),
        _MapResult(),
        _MapResult(
            [{"id": replacement, "status": "active", "tombstoned": False}]
        ),
    )

    memory = await memory_service.get_operator_memory(session, uuid4(), row.id)

    assert memory.id == row.id
    assert memory.lineage.tip is not None
    assert memory.lineage.tip.id == replacement
    assert memory.lineage.tip.tombstoned is False
    assert memory.lineage.replaces == []
    assert memory.lineage.edges_truncated is False
    assert memory.tags == ["support", "billing"]
    assert memory.confidence == 0.9
    assert memory.content_tokens == 21
    assert memory.pii_detected is True
    assert memory.pii_redacted is True
    dumped = memory.model_dump()
    assert "content" not in dumped
    assert "metadata" not in dumped


@pytest.mark.asyncio
async def test_list_memories_forwards_filters_and_builds_the_next_cursor() -> None:
    first, second = memory_row(), memory_row(created_at=NOW)
    session = _session([first, second])
    args = _args(
        limit=1,
        filters=MemoryListFilters(
            agent_id=uuid4(),
            session_id=uuid4(),
            status="archived",
            category="behavioral",
        ),
    )

    page = await memory_service.list_operator_memories(session, args)

    assert [memory.id for memory in page.data] == [first.id]
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
    assert params["session_id"] == args.filters.session_id
    assert params["status"] == "archived"
    assert params["category"] == "behavioral"
    assert "cursor_created_at" not in params
    assert "cursor_id" not in params


@pytest.mark.asyncio
async def test_list_memories_applies_a_decoded_cursor_and_reports_no_next_page() -> None:
    row = memory_row()
    cursor = encode_cursor({"created_at": NOW.isoformat(), "id": str(uuid4())})
    session = _session([row])

    page = await memory_service.list_operator_memories(session, _args(cursor=cursor, limit=50))

    assert page.pagination.has_more is False
    assert page.pagination.next_cursor is None
    params = session.execute.call_args.args[1]
    assert params["cursor_created_at"] == NOW
    assert params["cursor_id"] == UUID(decode_cursor(cursor)["id"])


@pytest.mark.asyncio
async def test_list_memories_accepts_dict_rows() -> None:
    row = memory_row()
    session = _session([row.__dict__])

    page = await memory_service.list_operator_memories(session, _args())

    assert page.data[0].id == row.id


@pytest.mark.asyncio
async def test_tags_are_sanitized_and_non_list_values_are_ignored() -> None:
    row = memory_row(tags=["support", "", 7, "billing"])
    session = _session([row])

    page = await memory_service.list_operator_memories(session, _args())

    assert page.data[0].tags == ["support", "billing"]


@pytest.mark.asyncio
async def test_persisted_metadata_is_normalized_to_the_contract() -> None:
    row = memory_row(
        visibility="public",
        tags=["support", "x" * 80, *(f"tag-{index}" for index in range(40))],
    )
    session = _session([row])

    page = await memory_service.list_operator_memories(session, _args())

    projected = page.data[0]
    assert projected.visibility == "agent"
    assert len(projected.tags) == 32
    assert projected.tags[1] == "x" * 64
    assert all(len(tag) <= 64 for tag in projected.tags)


@pytest.mark.asyncio
async def test_tag_length_is_counted_in_code_points() -> None:
    # Pydantic max_length counts code points, and so does the Console contract
    # (services/console/shared/operator/contracts.ts). A 64-code-point emoji tag
    # is 128 UTF-16 units; both sides must accept it or the list 502s.
    emoji_tag = "🧠" * 64
    row = memory_row(tags=[emoji_tag])
    session = _session([row])

    page = await memory_service.list_operator_memories(session, _args())

    assert page.data[0].tags == [emoji_tag]


@pytest.mark.asyncio
async def test_malformed_tag_payload_becomes_empty() -> None:
    session = _session([memory_row(tags="[not-json")])

    page = await memory_service.list_operator_memories(session, _args())

    assert page.data[0].tags == []


@pytest.mark.asyncio
async def test_non_list_tags_become_empty() -> None:
    row = memory_row(tags={"unexpected": True})
    session = _session([row])

    page = await memory_service.list_operator_memories(session, _args())

    assert page.data[0].tags == []


@pytest.mark.asyncio
async def test_lineage_maps_edges_and_truncates_over_the_cap() -> None:
    row = memory_row(status="superseded", superseded_by=uuid4())
    successors = [
        {
            "memory_id": uuid4(),
            "relationship_type": "supersedes",
            "confidence": 0.9,
            "created_at": NOW,
            "status": "active",
            "tombstoned": False,
        }
        for _ in range(21)
    ]
    predecessors = [
        {
            "memory_id": uuid4(),
            "relationship_type": "merged_from",
            "confidence": 0.7,
            "created_at": NOW,
            "status": "deleted",
            "tombstoned": True,
        }
    ]
    session = _session(
        [row],
        _MapResult(scalar=str(row.superseded_by)),
        _MapResult(successors),
        _MapResult(predecessors),
        _MapResult(
            [{"id": row.superseded_by, "status": "active", "tombstoned": False}]
        ),
    )

    memory = await memory_service.get_operator_memory(session, uuid4(), row.id)

    assert memory.lineage.superseded_by is not None
    assert memory.lineage.superseded_by.id == row.superseded_by
    assert memory.lineage.merged_into is None
    assert len(memory.lineage.replaces) == 20
    assert memory.lineage.edges_truncated is True
    assert memory.lineage.replaced_by[0].relationship_type == "merged_from"
    # A deleted replacement stays visible as deleted rather than as a live link.
    assert memory.lineage.replaced_by[0].status == "deleted"
    assert memory.lineage.replaced_by[0].tombstoned is True
