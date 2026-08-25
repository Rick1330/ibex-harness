"""Tests for golden-signal HTTP metrics middleware."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY, generate_latest


def _counter_value(name: str, labels: dict[str, str]) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    return float(value) if value is not None else 0.0


def test_http_metrics_records_route() -> None:
    from app.http_metrics import HTTPMetricsMiddleware

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
    from app.http_metrics import HTTPMetricsMiddleware

    app = FastAPI()
    app.add_middleware(HTTPMetricsMiddleware)

    @app.get("/metrics")
    def metrics() -> dict[str, str]:
        return {"ok": "1"}

    with TestClient(app) as client:
        assert client.get("/metrics").status_code == 200
    body = generate_latest().decode()
    assert "ibex_embedder_http_requests_total" in body or "ibex_process_up" in body


def test_unmatched_route_label() -> None:
    from app.http_metrics import HTTPMetricsMiddleware

    app = FastAPI()
    app.add_middleware(HTTPMetricsMiddleware)

    with TestClient(app) as client:
        assert client.get("/no-such-route").status_code == 404
    body = generate_latest().decode()
    assert 'route="<unmatched>"' in body


def test_unhandled_exception_records_500() -> None:
    from app.http_metrics import HTTPMetricsMiddleware

    app = FastAPI()
    app.add_middleware(HTTPMetricsMiddleware)

    @app.get("/boom")
    def boom() -> dict[str, str]:
        raise RuntimeError("boom")

    before = _counter_value(
        "ibex_embedder_http_requests_total",
        {"method": "GET", "route": "/boom", "status": "500"},
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/boom").status_code == 500
    after = _counter_value(
        "ibex_embedder_http_requests_total",
        {"method": "GET", "route": "/boom", "status": "500"},
    )
    assert after >= before + 1.0
