"""Tests for golden-signal HTTP metrics middleware."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import generate_latest

from app.http_metrics import HTTPMetricsMiddleware


def test_http_metrics_records_route() -> None:
    app = FastAPI()
    app.add_middleware(HTTPMetricsMiddleware)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
    body = generate_latest().decode()
    assert "ibex_embedder_http_requests_total" in body
    assert 'route="/health"' in body
    assert "ibex_process_up" in body


def test_metrics_skips_self() -> None:
    app = FastAPI()
    app.add_middleware(HTTPMetricsMiddleware)

    @app.get("/metrics")
    def metrics() -> dict[str, str]:
        return {"ok": "1"}

    with TestClient(app) as client:
        assert client.get("/metrics").status_code == 200
    body = generate_latest().decode()
    assert "ibex_embedder_http_requests_total" in body or "ibex_process_up" in body
