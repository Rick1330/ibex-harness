"""Unit tests for the metadata-only operator directive read service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from apierror_py import NOT_FOUND

from app.errors import ApiError
from app.services import operator_directives as directive_service
from app.services.operator_directives import DirectiveDetailArgs, DirectiveListArgs, usage_window

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


class _Result:
    """One fake result: mapping rows, or a scalar for the COUNT query."""

    def __init__(
        self, rows: list[dict[str, object]] | None = None, scalar: int = 0
    ) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def mappings(self) -> _Result:
        return self

    def all(self) -> list[dict[str, object]]:
        return list(self._rows)

    def first(self) -> dict[str, object] | None:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> int:
        return self._scalar


def _session(*results: list[dict[str, object]] | int) -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _Result(scalar=result) if isinstance(result, int) else _Result(result)
            for result in results
        ]
    )
    return session


def _list_args(**overrides: object) -> DirectiveListArgs:
    data: dict[str, object] = {
        "org_id": uuid4(),
        "state": "all",
        "agent_id": None,
        "cursor": None,
        "limit": 50,
    }
    data.update(overrides)
    return DirectiveListArgs(**data)  # type: ignore[arg-type]


def _header_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": uuid4(),
        "agent_id": uuid4(),
        "agent_name": "Support triage",
        "agent_slug": "support-triage",
        "is_active": True,
        "injection_mode": "system_first",
        "active_version_id": None,
        "updated_at": NOW,
    }
    row.update(overrides)
    return row


def _version_row(version_num: int, version_id: object, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": version_id,
        "version_num": version_num,
        "content_hash": f"{version_num:012d}" + "f" * 52,
        "content_bytes": 1024 + version_num,
        "created_by": uuid4(),
        "created_at": NOW - timedelta(days=10 - version_num),
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    ("range_value", "hours"),
    [("24h", 24), ("7d", 168), ("30d", 720)],
)
def test_usage_window_matches_the_requested_range(range_value: str, hours: int) -> None:
    start, end = usage_window(range_value, now=NOW)

    assert end == NOW
    assert start == NOW - timedelta(hours=hours)


@pytest.mark.asyncio
async def test_list_projects_the_live_pointer_not_the_newest_version() -> None:
    # A rollback moves the pointer back; the live version is v2 even though v5 is newest.
    session = _session(
        [
            {
                "id": uuid4(),
                "agent_id": uuid4(),
                "agent_name": "Support triage",
                "agent_slug": "support-triage",
                "is_active": True,
                "injection_mode": "system_first",
                "updated_at": NOW,
                "version_count": 5,
                "last_version_at": NOW - timedelta(hours=1),
                "active_version_num": 2,
            }
        ]
    )

    page = await directive_service.list_operator_directives(session, _list_args())

    row = page.data[0]
    assert page.observed_at is not None
    assert row.active_version_num == 2
    assert row.version_count == 5
    assert row.agent_name == "Support triage"
    assert page.pagination.has_more is False


@pytest.mark.asyncio
async def test_an_inactive_directive_reports_no_live_version() -> None:
    session = _session(
        [
            {
                "id": uuid4(),
                "agent_id": uuid4(),
                "agent_name": "Paused agent",
                "agent_slug": "paused-agent",
                "is_active": False,
                "injection_mode": "system_append",
                "updated_at": NOW,
                "version_count": 3,
                "last_version_at": NOW,
                "active_version_num": 3,
            }
        ]
    )

    page = await directive_service.list_operator_directives(session, _list_args())

    assert page.data[0].is_active is False
    assert page.data[0].active_version_num is None


@pytest.mark.asyncio
async def test_list_forwards_org_filters_and_cursor() -> None:
    session = _session([])
    args = _list_args(state="active", agent_id=uuid4(), cursor=None)
    from app.pagination import encode_cursor

    args = DirectiveListArgs(
        org_id=args.org_id,
        state="active",
        agent_id=args.agent_id,
        cursor=encode_cursor(
            {"created_at": NOW.isoformat(), "id": str(uuid4())}
        ),
        limit=10,
    )

    await directive_service.list_operator_directives(session, args)

    params = session.execute.await_args.args[1]
    assert params["org_id"] == args.org_id
    assert params["agent_id"] == args.agent_id
    assert params["cursor_updated_at"] == NOW
    assert params["limit"] == 11


@pytest.mark.asyncio
async def test_detail_marks_the_pointer_version_live_and_never_selects_content() -> None:
    live_id = uuid4()
    newer_id = uuid4()
    session = _session(
        [_header_row(active_version_id=live_id)],
        [
            _version_row(5, newer_id),
            _version_row(2, live_id),
        ],
        2,
        [{"version_num": 2, "sessions": 7, "last_session_at": NOW}],
        7,
    )

    detail = await directive_service.get_operator_directive(
        session, DirectiveDetailArgs(org_id=uuid4(), directive_id=uuid4(), usage_range="7d"), now=NOW
    )

    assert detail.usage_total_sessions == 7
    assert detail.usage_truncated is False
    assert detail.active_version_num == 2
    assert [version.version_num for version in detail.versions] == [5, 2]
    assert [version.is_live for version in detail.versions] == [False, True]
    # Digest is a short identity prefix, never the stored hash.
    assert all(len(version.content_digest) == 12 for version in detail.versions)
    assert detail.usage[0].version_num == 2
    assert detail.usage[0].sessions == 7
    assert detail.usage_range == "7d"
    # The version query asks for a byte count, not the instruction text.
    versions_sql = str(session.execute.await_args_list[1].args[0])
    assert "octet_length" in versions_sql
    assert "directive_versions.content " not in versions_sql


@pytest.mark.asyncio
async def test_detail_flags_a_pointer_that_names_a_missing_version() -> None:
    missing_id = uuid4()
    session = _session(
        [_header_row(active_version_id=missing_id)],
        [_version_row(1, uuid4())],
        1,
        [],
        [],
        0,
    )

    detail = await directive_service.get_operator_directive(
        session, DirectiveDetailArgs(org_id=uuid4(), directive_id=uuid4(), usage_range="24h"), now=NOW
    )

    assert detail.active_version_num is None
    assert detail.active_version_missing is True


@pytest.mark.asyncio
async def test_detail_is_not_found_for_another_tenant() -> None:
    session = _session([])

    with pytest.raises(ApiError) as err:
        await directive_service.get_operator_directive(
            session,
            DirectiveDetailArgs(org_id=uuid4(), directive_id=uuid4(), usage_range="7d"),
            now=NOW,
        )

    assert err.value.code == NOT_FOUND


@pytest.mark.asyncio
async def test_detail_usage_is_scoped_by_the_query_not_by_the_timeline() -> None:
    live_id = uuid4()
    session = _session(
        [_header_row(active_version_id=live_id)],
        [_version_row(1, live_id)],
        1,
        [
            {"version_num": 1, "sessions": 2, "last_session_at": NOW},
            {"version_num": 40, "sessions": 5, "last_session_at": NOW},
        ],
        7,
    )

    detail = await directive_service.get_operator_directive(
        session, DirectiveDetailArgs(org_id=uuid4(), directive_id=uuid4(), usage_range="7d"), now=NOW
    )

    # Usage is joined to the directive's versions in SQL, so a version outside the
    # listed timeline is still named, and the total stays exact.
    assert [(row.version_num, row.sessions) for row in detail.usage] == [(40, 5), (1, 2)]
    assert detail.usage_total_sessions == 7
    usage_sql = str(session.execute.await_args_list[3].args[0])
    assert "directive_versions" in usage_sql
