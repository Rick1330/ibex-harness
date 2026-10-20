"""Audit sink selection and metadata-only emission."""

from __future__ import annotations

from uuid import UUID

import pytest
from mcp_gateway import ToolAuditEvent

from app.audit import (
    ClickHouseOperatorAuditSink,
    LoggingOperatorAuditSink,
    build_operator_audit_sink,
)

ORG = UUID("11111111-1111-1111-1111-111111111111")


def _event() -> ToolAuditEvent:
    return ToolAuditEvent(
        request_id="req-1",
        org_id=ORG,
        tool_name="session.get",
        decision="allow",
        success=True,
        latency_ms=4,
        descriptor_hash="sha256:abc",
        scope="operator.read",
        scope_ok=True,
    )


def test_build_selects_logging_sink_when_unset() -> None:
    assert isinstance(build_operator_audit_sink(""), LoggingOperatorAuditSink)


def test_build_selects_clickhouse_sink_when_set() -> None:
    sink = build_operator_audit_sink("http://default:ibexdev@127.0.0.1:8123")
    assert isinstance(sink, ClickHouseOperatorAuditSink)


@pytest.mark.asyncio
async def test_logging_sink_write_is_noop_safe() -> None:
    sink = LoggingOperatorAuditSink()
    await sink.write(_event())
    await sink.aclose()


@pytest.mark.asyncio
async def test_clickhouse_sink_posts_json_each_row() -> None:
    captured: dict[str, object] = {}

    class _Response:
        status_code = 200

    class _Client:
        async def post(self, url: str, *, params: object, json: object) -> _Response:
            captured["url"] = url
            captured["params"] = params
            captured["json"] = json
            return _Response()

        async def aclose(self) -> None:
            captured["closed"] = True

    sink = ClickHouseOperatorAuditSink("http://clickhouse:8123")
    sink._client = _Client()  # type: ignore[assignment]
    await sink.write(_event())
    await sink.aclose()

    assert captured["url"] == "http://clickhouse:8123"
    assert "mcp_tool_calls" in str(captured["params"])
    row = captured["json"]
    assert isinstance(row, dict)
    assert row["tool_name"] == "session.get"
    assert "content" not in row
    assert captured["closed"] is True


@pytest.mark.asyncio
async def test_clickhouse_sink_hides_transport_error_details() -> None:
    class _Client:
        async def post(self, url: str, *, params: object, json: object):
            raise RuntimeError("connection to http://default:secret@clickhouse:8123 failed")

        async def aclose(self) -> None:
            return None

    sink = ClickHouseOperatorAuditSink("http://clickhouse:8123")
    sink._client = _Client()  # type: ignore[assignment]
    with pytest.raises(RuntimeError) as excinfo:
        await sink.write(_event())
    assert "secret" not in str(excinfo.value)


@pytest.mark.asyncio
async def test_clickhouse_sink_reports_status_without_body() -> None:
    class _Response:
        status_code = 500

    class _Client:
        async def post(self, url: str, *, params: object, json: object) -> _Response:
            return _Response()

        async def aclose(self) -> None:
            return None

    sink = ClickHouseOperatorAuditSink("http://clickhouse:8123")
    sink._client = _Client()  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="status=500"):
        await sink.write(_event())


def test_log_fields_include_caller_identity() -> None:
    from mcp_gateway import ToolAuditEvent

    event = ToolAuditEvent(
        request_id="req-2",
        org_id=ORG,
        tool_name="session.get",
        decision="allow",
        success=True,
        latency_ms=4,
        principal_id="user-1",
        token_id="token-1",
    )
    fields = event.as_log_fields()
    assert fields["principal_id"] == "user-1"
    assert fields["token_id"] == "token-1"
