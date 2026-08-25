"""Tests for golden-signal HTTP metrics middleware."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import generate_latest

from app.http_metrics import HTTPMetricsMiddleware


def test_http_metrics_collapses_mcp_path() -> None:
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
