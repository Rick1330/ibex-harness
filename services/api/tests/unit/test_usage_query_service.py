"""Unit tests for usage_query service helpers (4.P.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.errors import ApiError
from app.schemas.billing import UsageQueryRequest
from app.services import usage_query as uq


def test_inflight_key_tenant_prefix() -> None:
    org = uuid4()
    assert uq.inflight_key(org) == f"org_id:{org}:usagequery:inflight"


def test_validate_query_rejects_wide_range() -> None:
    body = UsageQueryRequest(
        shape="org_time_aggregate",
        start=datetime.now(UTC) - timedelta(days=40),
        end=datetime.now(UTC),
    )
    with pytest.raises(ApiError):
        uq.validate_query(uuid4(), body)


def test_validate_query_requires_request_id() -> None:
    body = UsageQueryRequest(
        shape="request_point_lookup",
        start=datetime.now(UTC) - timedelta(hours=1),
        end=datetime.now(UTC),
    )
    with pytest.raises(ApiError):
        uq.validate_query(uuid4(), body)


def test_derive_completeness() -> None:
    assert uq._derive_completeness([]) == "partial"
    assert uq._derive_completeness([{"completeness": "complete"}]) == "complete"
    assert uq._derive_completeness(
        [{"completeness": "complete"}, {"completeness": "partial"}]
    ) == "partial"


def test_bind_literals_agent_pred() -> None:
    agent = uuid4()
    org = uuid4()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=1)
    body = UsageQueryRequest(
        shape="agent_session_breakdown",
        start=start,
        end=end,
        agent_id=agent,
        limit=10,
    )
    sql = uq._bind_literals(uq._SQL_AGENT, org, body, 10)
    assert f"toUUID('{agent}')" in sql
    assert f"toUUID('{org}')" in sql


def test_bind_literals_tool_join() -> None:
    org = uuid4()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=1)
    body = UsageQueryRequest(
        shape="tool_correlation",
        start=start,
        end=end,
        limit=5,
    )
    sql = uq._bind_literals(uq._SQL_TOOL, org, body, 5)
    assert "mcp_tool_calls" in sql
    assert "tool_name" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rows", "expect_truncated", "expect_completeness"),
    [
        (
            [
                {"completeness": "complete"},
                {"completeness": "complete"},
                {"completeness": "partial"},
            ],
            True,
            "complete",
        ),
        (
            [{"completeness": "partial"}, {"completeness": "partial"}],
            False,
            "partial",
        ),
    ],
)
async def test_execute_usage_query_truncation(
    rows: list[dict], expect_truncated: bool, expect_completeness: str
) -> None:
    org = uuid4()
    body = UsageQueryRequest(
        shape="org_time_aggregate",
        start=datetime.now(UTC) - timedelta(hours=1),
        end=datetime.now(UTC),
        limit=2,
    )
    with (
        patch("app.services.usage_query._acquire_inflight", new=AsyncMock()),
        patch("app.services.usage_query._release_inflight", new=AsyncMock()),
        patch("app.services.usage_query._run_clickhouse", new=AsyncMock(return_value=rows)),
    ):
        out = await uq.execute_usage_query(
            org_id=org, body=body, redis_url=None, clickhouse_url=None
        )
    assert out.truncated is expect_truncated
    assert len(out.rows) == 2
    assert out.completeness == expect_completeness


@pytest.mark.asyncio
async def test_run_clickhouse_empty_without_dsn() -> None:
    body = UsageQueryRequest(
        shape="org_time_aggregate",
        start=datetime.now(UTC) - timedelta(hours=1),
        end=datetime.now(UTC),
        limit=10,
    )
    with patch.dict(
        "os.environ",
        {"CLICKHOUSE_HTTP_URL": "", "IBEX_CLICKHOUSE_HTTP_URL": ""},
        clear=False,
    ):
        rows = await uq._run_clickhouse(uuid4(), body, 10, None)
    assert rows == []


@pytest.mark.asyncio
async def test_acquire_inflight_too_many() -> None:
    client = MagicMock()
    client.eval = AsyncMock(return_value=-1)
    client.aclose = AsyncMock()
    with (
        patch("app.services.usage_query._redis_client", return_value=client),
        pytest.raises(ApiError),
    ):
        await uq._acquire_inflight("redis://localhost", uuid4())


@pytest.mark.asyncio
async def test_release_inflight_swallows_redis_error() -> None:
    from redis.exceptions import RedisError

    client = MagicMock()
    client.decr = AsyncMock(side_effect=RedisError("down"))
    client.aclose = AsyncMock()
    with patch("app.services.usage_query._redis_client", return_value=client):
        await uq._release_inflight("redis://localhost", uuid4())


@pytest.mark.asyncio
async def test_run_clickhouse_parses_rows() -> None:
    body = UsageQueryRequest(
        shape="org_time_aggregate",
        start=datetime.now(UTC) - timedelta(hours=1),
        end=datetime.now(UTC),
        limit=10,
    )
    resp = MagicMock()
    resp.status_code = 200
    resp.text = '{"bucket":"2026-01-01 00:00:00","completeness":"partial"}\n'
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=resp)
    with patch("httpx.AsyncClient", return_value=client):
        rows = await uq._run_clickhouse(uuid4(), body, 10, "http://localhost:8123")
    assert len(rows) == 1
    assert rows[0]["completeness"] == "partial"


@pytest.mark.asyncio
async def test_run_clickhouse_http_error() -> None:
    body = UsageQueryRequest(
        shape="request_point_lookup",
        start=datetime.now(UTC) - timedelta(hours=1),
        end=datetime.now(UTC),
        request_id="req-1",
        limit=1,
    )
    resp = MagicMock()
    resp.status_code = 500
    resp.text = "boom"
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=resp)
    with patch("httpx.AsyncClient", return_value=client), pytest.raises(ApiError):
        await uq._run_clickhouse(uuid4(), body, 1, "http://localhost:8123")


def test_validate_query_ok_defaults() -> None:
    body = UsageQueryRequest(
        shape="org_time_aggregate",
        start=datetime.now(UTC) - timedelta(hours=1),
        end=datetime.now(UTC),
    )
    assert uq.validate_query(uuid4(), body) == uq._MAX_ROWS


def test_fmt_ts_naive() -> None:
    ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC).replace(tzinfo=None)
    assert "2026-01-01" in uq._fmt_ts(ts)

def test_parse_clickhouse_rows_empty_lines() -> None:
    rows = uq._parse_clickhouse_rows(200, '\n\n{"x":1}\n')
    assert rows == [{"x": 1}]


def test_parse_clickhouse_rows_bad_json() -> None:
    with pytest.raises(ApiError):
        uq._parse_clickhouse_rows(200, "not-json\n")


def test_parse_clickhouse_rows_http_error() -> None:
    with pytest.raises(ApiError):
        uq._parse_clickhouse_rows(500, "boom")


@pytest.mark.asyncio
async def test_run_clickhouse_transport_error() -> None:
    import httpx

    body = UsageQueryRequest(
        shape="org_time_aggregate",
        start=datetime.now(UTC) - timedelta(hours=1),
        end=datetime.now(UTC),
        limit=10,
    )
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(side_effect=httpx.ConnectError("down"))
    with patch("httpx.AsyncClient", return_value=client), pytest.raises(ApiError):
        await uq._run_clickhouse(uuid4(), body, 10, "http://localhost:8123")


@pytest.mark.asyncio
async def test_acquire_inflight_redis_error() -> None:
    from redis.exceptions import RedisError

    client = MagicMock()
    client.eval = AsyncMock(side_effect=RedisError("down"))
    client.aclose = AsyncMock()
    with (
        patch("app.services.usage_query._redis_client", return_value=client),
        pytest.raises(ApiError),
    ):
        await uq._acquire_inflight("redis://localhost", uuid4())


def test_bind_literals_agent_and_request() -> None:
    org = uuid4()
    agent = uuid4()
    body = UsageQueryRequest(
        shape="agent_session_breakdown",
        start=datetime.now(UTC) - timedelta(hours=1),
        end=datetime.now(UTC),
        agent_id=agent,
        request_id="req'1",
        limit=5,
    )
    sql = (
        "WHERE org={org_id:UUID} {agent_pred} AND t>={start:DateTime64(3)} "
        "AND t<{end:DateTime64(3)} AND rid={request_id:String} "
        "LIMIT {limit:UInt32} MAX {max_rows:UInt64}"
    )
    out = uq._bind_literals(sql, org, body, 5)
    assert str(org) in out
    assert str(agent) in out
    assert "LIMIT 5" in out


def test_validate_query_request_id_required() -> None:
    body = UsageQueryRequest(
        shape="request_point_lookup",
        start=datetime.now(UTC) - timedelta(hours=1),
        end=datetime.now(UTC),
    )
    with pytest.raises(ApiError):
        uq.validate_query(uuid4(), body)


def test_derive_completeness_empty_and_mixed() -> None:
    assert uq._derive_completeness([]) == "partial"
    assert uq._derive_completeness([{"completeness": "complete"}]) == "complete"
    assert (
        uq._derive_completeness(
            [{"completeness": "complete"}, {"completeness": "partial"}]
        )
        == "partial"
    )
