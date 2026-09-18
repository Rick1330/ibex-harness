"""Unit tests for usage_query service helpers (4.P.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.errors import ApiError
from app.schemas.billing import UsageQueryRequest
from app.services import usage_query as uq


def _window(hours: float = 1.0) -> tuple[datetime, datetime]:
    end = datetime.now(UTC)
    return end - timedelta(hours=hours), end


def _body(shape: str = "org_time_aggregate", **kwargs: Any) -> UsageQueryRequest:
    start, end = _window()
    return UsageQueryRequest(shape=shape, start=start, end=end, **kwargs)


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
    with pytest.raises(ApiError):
        uq.validate_query(uuid4(), _body("request_point_lookup"))


def test_validate_query_ok_defaults() -> None:
    assert uq.validate_query(uuid4(), _body()) == uq._MAX_ROWS


def test_derive_completeness() -> None:
    assert uq._derive_completeness([]) == "partial"
    assert uq._derive_completeness([{"completeness": "complete"}]) == "complete"
    assert (
        uq._derive_completeness(
            [{"completeness": "complete"}, {"completeness": "partial"}]
        )
        == "partial"
    )


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


def test_bind_literals_agent_and_request() -> None:
    org = uuid4()
    agent = uuid4()
    body = _body(
        "agent_session_breakdown",
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
    body = _body(limit=2)
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


def _mock_httpx_client(resp: MagicMock | None = None, post_side_effect: Exception | None = None):
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    if post_side_effect is not None:
        client.post = AsyncMock(side_effect=post_side_effect)
    else:
        client.post = AsyncMock(return_value=resp)
    return client


def _mock_redis_client(**attrs: Any) -> MagicMock:
    client = MagicMock()
    client.aclose = AsyncMock()
    for name, value in attrs.items():
        setattr(client, name, value)
    return client


@pytest.mark.asyncio
async def test_run_clickhouse_empty_without_dsn() -> None:
    with patch.dict(
        "os.environ",
        {"CLICKHOUSE_HTTP_URL": "", "IBEX_CLICKHOUSE_HTTP_URL": ""},
        clear=False,
    ):
        rows = await uq._run_clickhouse(uuid4(), _body(limit=10), 10, None)
    assert rows == []


@pytest.mark.asyncio
async def test_acquire_inflight_too_many() -> None:
    client = _mock_redis_client(eval=AsyncMock(return_value=-1))
    with (
        patch("app.services.usage_query._redis_client", return_value=client),
        pytest.raises(ApiError),
    ):
        await uq._acquire_inflight("redis://localhost", uuid4())


@pytest.mark.asyncio
async def test_release_inflight_swallows_redis_error() -> None:
    from redis.exceptions import RedisError

    client = _mock_redis_client(decr=AsyncMock(side_effect=RedisError("down")))
    with patch("app.services.usage_query._redis_client", return_value=client):
        await uq._release_inflight("redis://localhost", uuid4())


@pytest.mark.asyncio
async def test_run_clickhouse_parses_rows() -> None:
    resp = MagicMock(status_code=200, text='{"bucket":"2026-01-01 00:00:00","completeness":"partial"}\n')
    with patch("httpx.AsyncClient", return_value=_mock_httpx_client(resp)):
        rows = await uq._run_clickhouse(uuid4(), _body(limit=10), 10, "http://localhost:8123")
    assert len(rows) == 1
    assert rows[0]["completeness"] == "partial"


@pytest.mark.asyncio
async def test_run_clickhouse_http_error() -> None:
    resp = MagicMock(status_code=500, text="boom")
    body = _body("request_point_lookup", request_id="req-1", limit=1)
    with patch("httpx.AsyncClient", return_value=_mock_httpx_client(resp)), pytest.raises(ApiError):
        await uq._run_clickhouse(uuid4(), body, 1, "http://localhost:8123")


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

    with (
        patch(
            "httpx.AsyncClient",
            return_value=_mock_httpx_client(post_side_effect=httpx.ConnectError("down")),
        ),
        pytest.raises(ApiError),
    ):
        await uq._run_clickhouse(uuid4(), _body(limit=10), 10, "http://localhost:8123")


@pytest.mark.asyncio
async def test_acquire_inflight_redis_error() -> None:
    from redis.exceptions import RedisError

    client = _mock_redis_client(eval=AsyncMock(side_effect=RedisError("down")))
    with (
        patch("app.services.usage_query._redis_client", return_value=client),
        pytest.raises(ApiError),
    ):
        await uq._acquire_inflight("redis://localhost", uuid4())
