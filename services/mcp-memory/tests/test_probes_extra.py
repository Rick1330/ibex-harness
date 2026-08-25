"""Logging audit sink and readiness probe edge cases."""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.audit import LoggingAuditSink, ToolCallAuditEvent
from app.auth import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.main import create_app
from app.permissions import MEMORY_READ
from app.state import AppState

ORG = UUID("11111111-1111-1111-1111-111111111111")


@pytest.mark.asyncio
async def test_logging_sink_writes_metadata_only(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    caplog.set_level(logging.INFO)
    sink = LoggingAuditSink()
    await sink.write(
        ToolCallAuditEvent(
            request_id="r1",
            org_id=ORG,
            tool_name="search_memory",
            latency_ms=3,
            success=True,
        )
    )
    assert "search_memory" in caplog.text
    assert str(ORG) in caplog.text


def test_ready_503_when_not_ready() -> None:
    settings = Settings(resource_url="http://testserver/mcp")
    validator = StaticTokenValidator(
        {"t": ValidateResult(org_id=ORG, permissions=MEMORY_READ)},
        available=True,
    )
    application = create_app(settings=settings, validator=validator)
    with TestClient(application) as client:
        state: AppState = application.state.mcp
        state.ready = False
        state.ready_error = "auth gRPC not reachable"
        resp = client.get("/ready")
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "service_not_ready"
