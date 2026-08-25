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


def test_ready_503_when_auth_unreachable() -> None:
    settings = Settings(resource_url="http://testserver/mcp")
    validator = StaticTokenValidator(
        {"t": ValidateResult(org_id=ORG, permissions=MEMORY_READ)},
        available=False,
    )
    application = create_app(settings=settings, validator=validator)
    with TestClient(application) as client:
        resp = client.get("/ready")
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "service_not_ready"
        assert "auth" in resp.json()["error"]["message"].lower()


def test_ready_recovers_when_auth_becomes_available() -> None:
    settings = Settings(resource_url="http://testserver/mcp")
    validator = StaticTokenValidator(
        {"t": ValidateResult(org_id=ORG, permissions=MEMORY_READ)},
        available=False,
    )
    application = create_app(settings=settings, validator=validator)
    with TestClient(application) as client:
        assert client.get("/ready").status_code == 503
        validator.set_available(True)
        resp = client.get("/ready")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"
