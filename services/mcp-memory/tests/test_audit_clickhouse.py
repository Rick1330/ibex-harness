"""ClickHouse audit sink and row shaping tests."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.audit import (
    ClickHouseHTTPAuditSink,
    LoggingAuditSink,
    ToolCallAuditEvent,
    build_audit_sink,
)

ORG = UUID("11111111-1111-1111-1111-111111111111")


def test_build_audit_sink_defaults_to_logging() -> None:
    assert isinstance(build_audit_sink(""), LoggingAuditSink)
    assert isinstance(build_audit_sink("http://localhost:8123"), ClickHouseHTTPAuditSink)


def test_as_clickhouse_row_has_no_content_keys() -> None:
    row = ToolCallAuditEvent(
        request_id="r1",
        org_id=ORG,
        tool_name="search_memory",
        latency_ms=12,
        success=True,
        requested_at=datetime(2026, 8, 25, 12, 0, 0, tzinfo=UTC),
    ).as_clickhouse_row()
    assert "content" not in row
    assert "query" not in row
    assert row["org_id"] == str(ORG)
    assert row["tool_name"] == "search_memory"


@pytest.mark.asyncio
async def test_clickhouse_sink_posts_json_row() -> None:
    sink = ClickHouseHTTPAuditSink("http://clickhouse:8123")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    sink._client = AsyncMock()
    sink._client.post = AsyncMock(return_value=mock_response)
    sink._client.aclose = AsyncMock()

    await sink.write(
        ToolCallAuditEvent(
            request_id="r1",
            org_id=ORG,
            tool_name="write_memory",
            latency_ms=4,
            success=True,
        )
    )
    assert sink._client.post.await_count == 1
    kwargs = sink._client.post.await_args.kwargs
    assert "mcp_tool_calls" in kwargs["params"]["query"]
    assert kwargs["json"]["org_id"] == str(ORG)
    await sink.aclose()
