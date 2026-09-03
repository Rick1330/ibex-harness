"""Unit tests for llm_traces HTTP insert (no live ClickHouse)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from app.extraction.clickhouse_traces import (
    ExtractionTraceRow,
    MissingOrgIdError,
    insert_extraction_trace,
)


def _row(**overrides: object) -> ExtractionTraceRow:
    base = {
        "request_id": "req-1",
        "org_id": uuid4(),
        "agent_id": uuid4(),
        "session_id": uuid4(),
        "model": "gpt-4o-mini",
        "provider": "openai",
        "input_tokens": 10,
        "output_tokens": 4,
        "provider_ttfb_ms": 12,
        "total_latency_ms": 12,
        "status_code": 200,
        "is_complete": True,
        "error_code": "",
        "requested_at": datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
        "completed_at": datetime(2026, 9, 3, 12, 0, 1, tzinfo=UTC),
    }
    base.update(overrides)
    return ExtractionTraceRow(**base)  # type: ignore[arg-type]


def test_empty_dsn_skips() -> None:
    assert insert_extraction_trace(dsn=None, row=_row()) is False
    assert insert_extraction_trace(dsn="  ", row=_row()) is False


def test_insert_posts_json_each_row_without_content() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode()
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    row = _row()
    assert insert_extraction_trace(
        dsn="clickhouse://default:s3cret@localhost:8123/ibex",
        row=row,
        client=client,
    )
    body = json.loads(str(captured["body"]).strip())
    assert "prompt" not in body
    assert "completion" not in body
    assert "content" not in body
    assert body["org_id"] == str(row.org_id)
    assert body["is_streaming"] is False
    assert body["total_tokens"] == 14
    assert "FORMAT JSONEachRow" in str(captured["query"]["query"])


def test_http_error_fail_open() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="busy")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert (
        insert_extraction_trace(
            dsn="clickhouse://default:@localhost:8123/ibex",
            row=_row(),
            client=client,
        )
        is False
    )


def test_refuse_without_org_id() -> None:
    with pytest.raises(MissingOrgIdError, match="org_id"):
        insert_extraction_trace(dsn="clickhouse://default:@localhost:8123/ibex", row=_row(org_id=None))
