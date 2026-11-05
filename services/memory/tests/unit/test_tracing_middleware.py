"""OpenTelemetry ASGI middleware tests for memory."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from app.http_metrics import http_method, instrument_scope, route_label, route_template
from app.tracing import TracingMiddleware
from tests.unit.tracing_support import (
    SPAN_ID,
    TRACE_ID,
    _clear_spans,
    _only_span,
    exporter,
)

# Keep the imported fixtures referenced so ruff does not treat them as unused;
# pytest resolves them from the module namespace.
_TRACING_FIXTURES = (exporter, _clear_spans)

pytestmark = pytest.mark.usefixtures("exporter")


# ---------------------------------------------------------------------------
# 5-7, 13: HTTP middleware
# ---------------------------------------------------------------------------


def test_incoming_traceparent_is_continued(exporter: InMemorySpanExporter) -> None:
    application = FastAPI()
    application.add_middleware(TracingMiddleware)

    @application.get("/ping")
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    with TestClient(application) as client:
        response = client.get(
            "/ping",
            headers={"traceparent": f"00-{TRACE_ID}-{SPAN_ID}-01"},
        )

    assert response.status_code == 200
    span = _only_span(exporter, "memory.http")
    assert format(span.context.trace_id, "032x") == TRACE_ID
    assert format(span.parent.span_id, "016x") == SPAN_ID
    assert span.attributes["http.request.method"] == "GET"
    assert span.attributes["http.response.status_code"] == 200


def test_route_template_is_recorded_instead_of_raw_path(
    exporter: InMemorySpanExporter,
) -> None:
    memory_id = str(uuid4())
    application = FastAPI()
    application.add_middleware(TracingMiddleware)

    @application.get("/v1/memories/{memory_id}/forget")
    def forget(memory_id: str) -> dict[str, str]:
        return {"memory_id": memory_id}

    with TestClient(application) as client:
        assert client.get(f"/v1/memories/{memory_id}/forget").status_code == 200

    span = _only_span(exporter, "memory.http")
    assert span.attributes["http.route"] == "/v1/memories/{memory_id}/forget"
    assert "url.path" not in span.attributes
    assert all(memory_id not in str(value) for value in span.attributes.values())


def test_unmatched_route_omits_http_route(exporter: InMemorySpanExporter) -> None:
    application = FastAPI()
    application.add_middleware(TracingMiddleware)

    with TestClient(application) as client:
        assert client.get("/does-not-exist").status_code == 404

    span = _only_span(exporter, "memory.http")
    assert "http.route" not in span.attributes
    assert span.status.status_code is StatusCode.UNSET


def test_5xx_sets_error_status_without_description(exporter: InMemorySpanExporter) -> None:
    application = FastAPI()
    application.add_middleware(TracingMiddleware)

    @application.get("/unavailable")
    def unavailable() -> Response:
        return Response(status_code=503)

    with TestClient(application) as client:
        assert client.get("/unavailable").status_code == 503

    span = _only_span(exporter, "memory.http")
    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description is None
    assert span.events == ()


def test_unhandled_exception_records_class_name_only(exporter: InMemorySpanExporter) -> None:
    application = FastAPI()
    application.add_middleware(TracingMiddleware)

    @application.get("/explode")
    def explode() -> None:
        raise RuntimeError("sensitive context")

    with TestClient(application, raise_server_exceptions=False) as client:
        assert client.get("/explode").status_code == 500

    span = _only_span(exporter, "memory.http")
    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description == "RuntimeError"
    assert span.events == ()
    # ServerErrorMiddleware sits outside the tracing middleware, so the 500 is the
    # middleware's own record of what the client received.
    assert span.attributes["http.response.status_code"] == 500
    assert span.attributes["http.route"] == "/explode"


def test_unknown_http_method_is_bounded(exporter: InMemorySpanExporter) -> None:
    """A caller-chosen method token must not become a span attribute verbatim."""
    application = FastAPI()
    application.add_middleware(TracingMiddleware)

    @application.get("/ping")
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    with TestClient(application) as client:
        response = client.request("PURGE-X-4bf92f35", "/ping")

    assert response.status_code in {200, 405}
    span = _only_span(exporter, "memory.http")
    assert span.attributes["http.request.method"] == "_OTHER"


def test_http_method_helper_bounds_cardinality() -> None:
    assert http_method({"type": "http", "method": "GET"}) == "GET"
    assert http_method({"type": "http", "method": "3f2504e0-4f89-11d3"}) == "_OTHER"
    assert http_method({"type": "http"}) == "GET"
    assert http_method({"type": "http", "method": None}) == "_OTHER"


def test_metrics_path_is_not_traced(exporter: InMemorySpanExporter) -> None:
    application = FastAPI()
    application.add_middleware(TracingMiddleware)

    @application.get("/metrics")
    def metrics() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(application) as client:
        assert client.get("/metrics").status_code == 200

    assert exporter.get_finished_spans() == ()


@pytest.mark.asyncio
async def test_non_http_scope_passes_through(exporter: InMemorySpanExporter) -> None:
    seen: list[str] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        seen.append(scope["type"])

    async def receive() -> dict[str, Any]:
        return {"type": "lifespan.startup"}

    async def send(_message: Any) -> None:
        return None

    middleware = TracingMiddleware(app)
    await middleware({"type": "lifespan"}, receive, send)

    assert seen == ["lifespan"]
    assert exporter.get_finished_spans() == ()


def test_route_helpers_agree() -> None:
    matched = {"type": "http", "route": SimpleNamespace(path="/v1/memories/{memory_id}")}
    assert route_template(matched) == "/v1/memories/{memory_id}"
    assert route_label(matched) == "/v1/memories/{memory_id}"

    unmatched = {"type": "http", "route": SimpleNamespace(path="")}
    assert route_template(unmatched) is None
    assert route_label(unmatched) == "<unmatched>"
    assert instrument_scope(unmatched) is True
    assert instrument_scope({"type": "http", "path": "/metrics"}) is False
    assert instrument_scope({"type": "lifespan"}) is False
