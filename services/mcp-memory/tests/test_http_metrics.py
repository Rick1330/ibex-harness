"""Tests for golden-signal HTTP metrics middleware."""

from __future__ import annotations

import asyncio
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY, generate_latest
from starlette.responses import StreamingResponse

from app.audit import MemoryAuditSink
from app.auth import StaticTokenValidator, ValidateResult
from app.config import Settings, get_settings
from app.main import create_app
from app.permissions import MEMORY_READ, MEMORY_WRITE


def _counter_value(name: str, labels: dict[str, str]) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    return float(value) if value is not None else 0.0


def test_http_metrics_collapses_mcp_path() -> None:
    from app.http_metrics import HTTPMetricsMiddleware

    app = FastAPI()
    app.add_middleware(HTTPMetricsMiddleware)

    @app.post("/mcp")
    def mcp() -> dict[str, str]:
        return {"ok": "1"}

    with TestClient(app) as client:
        assert client.post("/mcp").status_code == 200
    body = generate_latest().decode()
    assert "ibex_mcp_http_requests_total" in body
    assert 'route="/mcp"' in body
    assert "ibex_process_up" in body


def test_unmatched_route_label() -> None:
    from app.http_metrics import HTTPMetricsMiddleware

    app = FastAPI()
    app.add_middleware(HTTPMetricsMiddleware)

    with TestClient(app) as client:
        assert client.get("/no-such-route").status_code == 404
    body = generate_latest().decode()
    assert 'route="<unmatched>"' in body


def test_streaming_duration_waits_for_body_complete() -> None:
    from app.http_metrics import HTTPMetricsMiddleware

    app = FastAPI()
    app.add_middleware(HTTPMetricsMiddleware)

    async def gen():
        yield b"a"
        await asyncio.sleep(0.05)
        yield b"b"

    @app.get("/stream")
    def stream() -> StreamingResponse:
        return StreamingResponse(gen(), media_type="text/plain")

    started = time.perf_counter()
    with TestClient(app) as client:
        resp = client.get("/stream")
        assert resp.status_code == 200
        assert resp.content == b"ab"
    elapsed = time.perf_counter() - started
    assert elapsed >= 0.04
    body = generate_latest().decode()
    assert 'route="/stream"' in body
    assert "ibex_mcp_http_request_duration_seconds" in body


def test_unauthorized_request_increments_metrics() -> None:
    get_settings.cache_clear()
    settings = Settings(
        transport="streamable_http",
        resource_url="http://testserver/mcp",
        auth_server_url="http://auth.test",
        auth_grpc_addr="127.0.0.1:1",
    )
    validator = StaticTokenValidator(
        {
            "tok": ValidateResult(
                org_id=__import__("uuid").UUID("11111111-1111-1111-1111-111111111111"),
                permissions=MEMORY_READ | MEMORY_WRITE,
            )
        }
    )
    application = create_app(settings=settings, validator=validator, audit_sink=MemoryAuditSink())
    before = _counter_value(
        "ibex_mcp_http_requests_total",
        {"method": "POST", "route": "/mcp", "status": "401"},
    )
    with TestClient(application) as client:
        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        assert resp.status_code == 401
    after = _counter_value(
        "ibex_mcp_http_requests_total",
        {"method": "POST", "route": "/mcp", "status": "401"},
    )
    assert after >= before + 1.0
    get_settings.cache_clear()
