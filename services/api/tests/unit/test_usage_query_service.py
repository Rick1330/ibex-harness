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
async def test_execute_usage_query_truncated_limit_plus_one() -> None:
    org = uuid4()
    start = datetime.now(UTC) - timedelta(hours=1)
    end = datetime.now(UTC)
    body = UsageQueryRequest(
        shape="org_time_aggregate",
        start=start,
        end=end,
        limit=2,
    )
    rows = [
        {"completeness": "complete"},
        {"completeness": "complete"},
        {"completeness": "partial"},
    ]
    with (
        patch("app.services.usage_query._acquire_inflight", new=AsyncMock()),
        patch("app.services.usage_query._release_inflight", new=AsyncMock()),
        patch("app.services.usage_query._run_clickhouse", new=AsyncMock(return_value=rows)),
    ):
        out = await uq.execute_usage_query(
            org_id=org, body=body, redis_url=None, clickhouse_url=None
        )
    assert out.truncated is True
    assert len(out.rows) == 2
    assert out.completeness == "complete"


@pytest.mark.asyncio
async def test_execute_usage_query_exact_limit_not_truncated() -> None:
    org = uuid4()
    start = datetime.now(UTC) - timedelta(hours=1)
    end = datetime.now(UTC)
    body = UsageQueryRequest(
        shape="org_time_aggregate",
        start=start,
        end=end,
        limit=2,
    )
    rows = [{"completeness": "partial"}, {"completeness": "partial"}]
    with (
        patch("app.services.usage_query._acquire_inflight", new=AsyncMock()),
        patch("app.services.usage_query._release_inflight", new=AsyncMock()),
        patch("app.services.usage_query._run_clickhouse", new=AsyncMock(return_value=rows)),
    ):
        out = await uq.execute_usage_query(
            org_id=org, body=body, redis_url=None, clickhouse_url=None
        )
    assert out.truncated is False
    assert len(out.rows) == 2


@pytest.mark.asyncio
async def test_run_clickhouse_empty_without_dsn() -> None:
    body = UsageQueryRequest(
        shape="org_time_aggregate",
        start=datetime.now(UTC) - timedelta(hours=1),
        end=datetime.now(UTC),
        limit=10,
    )
    with patch.dict("os.environ", {}, clear=False):
        rows = await uq._run_clickhouse(uuid4(), body, 10, None)
    assert rows == []


@pytest.mark.asyncio
async def test_acquire_inflight_too_many() -> None:
    client = MagicMock()
    client.incr = AsyncMock(return_value=5)
    client.expire = AsyncMock()
    client.decr = AsyncMock()
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