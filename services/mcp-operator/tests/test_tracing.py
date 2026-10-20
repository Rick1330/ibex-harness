"""Trace propagation and dependency-span coverage for the operator gateway."""

from __future__ import annotations

import asyncio
from uuid import UUID

import pytest
from authclient.validate import ValidateResult
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.auth import GRPCTokenValidator
from app.tracing import TracingMiddleware, _traces_endpoint, configure_tracing

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
SPAN_ID = "00f067aa0ba902b7"


@pytest.fixture(scope="module")
def exporter() -> InMemorySpanExporter:
    sink = InMemorySpanExporter()
    configure_tracing("").add_span_processor(SimpleSpanProcessor(sink))
    return sink


@pytest.fixture(autouse=True)
def _clear_spans(exporter: InMemorySpanExporter) -> None:
    exporter.clear()


def test_incoming_traceparent_is_continued(exporter: InMemorySpanExporter) -> None:
    app = FastAPI()
    app.add_middleware(TracingMiddleware)

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"ok": "1"}

    with TestClient(app) as client:
        response = client.get(
            "/ping",
            headers={"traceparent": f"00-{TRACE_ID}-{SPAN_ID}-01"},
        )
    assert response.status_code == 200
    spans = [s for s in exporter.get_finished_spans() if s.name == "mcp.http"]
    assert len(spans) == 1
    assert format(spans[0].context.trace_id, "032x") == TRACE_ID


def test_auth_validation_emits_dependency_span(exporter: InMemorySpanExporter) -> None:
    class _Inner:
        async def validate(self, _token: str) -> ValidateResult:
            return ValidateResult(
                org_id=UUID("11111111-1111-1111-1111-111111111111"),
                permissions=1,
                agent_id=None,
                user_id="user",
                token_id="token",
            )

        async def ready(self) -> bool:
            return True

        async def aclose(self) -> None:
            return None

    validator = GRPCTokenValidator.__new__(GRPCTokenValidator)
    validator._inner = _Inner()  # type: ignore[attr-defined]
    asyncio.run(validator.validate("opaque-token"))
    names = [s.name for s in exporter.get_finished_spans()]
    assert "auth.validate" in names


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        ("http://collector:4318", "http://collector:4318/v1/traces"),
        ("http://collector:4318/", "http://collector:4318/v1/traces"),
        ("http://collector:4318/v1/traces", "http://collector:4318/v1/traces"),
        ("http://collector:4318/v1/traces/", "http://collector:4318/v1/traces"),
        ("  http://collector:4318  ", "http://collector:4318/v1/traces"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_traces_endpoint_is_normalized(endpoint: str, expected: str) -> None:
    assert _traces_endpoint(endpoint) == expected
