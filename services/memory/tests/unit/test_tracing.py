"""OpenTelemetry trace propagation, dependency spans, and configuration tests for memory."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.clients.rerank import RerankTimeoutError
from app.read.full_text import FullTextHit
from app.tracing import (
    TracingMiddleware,
    _traces_endpoint,
    configure_tracing,
    get_tracer,
)
from app.vectorstore.base import SearchHit
from tests.unit.find_similar_support import (
    make_hydrated_map as _hydrated_map,
)
from tests.unit.find_similar_support import (
    make_query as _query,
)
from tests.unit.find_similar_support import (
    make_repo as _repo,
)
from tests.unit.find_similar_support import (
    make_result as _result,
)
from tests.unit.find_similar_support import (
    make_settings as _settings,
)

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
SPAN_ID = "00f067aa0ba902b7"


def _build_test_repo(
    ids: list[UUID],
    rerank_effect: object,
):
    store = MagicMock()
    store.search = AsyncMock(
        return_value=[SearchHit(memory_id=mid, similarity=0.9) for mid in ids]
    )
    rerank_client = MagicMock()
    rerank_client.host = "rerank.internal"
    if isinstance(rerank_effect, Exception):
        rerank_client.rerank = AsyncMock(side_effect=rerank_effect)
    else:
        rerank_client.rerank = AsyncMock(return_value=rerank_effect)

    settings = _settings(search_hybrid_enabled=True, rerank_enabled=True)
    repo = _repo(store, settings, rerank_client=rerank_client)
    repo._hydrate_hits = AsyncMock(
        side_effect=lambda **kwargs: _hydrated_map([_result(mid) for mid in ids])
    )
    return repo


@pytest.fixture(scope="module")
def exporter() -> InMemorySpanExporter:
    sink = InMemorySpanExporter()
    provider = configure_tracing("")
    provider.add_span_processor(SimpleSpanProcessor(sink))
    return sink


@pytest.fixture(autouse=True)
def _clear_spans(exporter: InMemorySpanExporter) -> None:
    exporter.clear()


def test_incoming_traceparent_is_continued(exporter: InMemorySpanExporter) -> None:
    app = FastAPI()
    app.add_middleware(TracingMiddleware)

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    with TestClient(app) as client:
        response = client.get(
            "/ping",
            headers={"traceparent": f"00-{TRACE_ID}-{SPAN_ID}-01"},
        )
    assert response.status_code == 200
    spans = [s for s in exporter.get_finished_spans() if s.name == "memory.http"]
    assert len(spans) == 1
    assert format(spans[0].context.trace_id, "032x") == TRACE_ID


def _assert_dependency_spans(spans: list[object], parent_trace_id: int) -> None:
    targets = {"vector_search", "full_text_search", "hydration", "rerank"}
    for span in spans:
        if getattr(span, "name", None) in targets:
            assert span.context.trace_id == parent_trace_id


def _assert_no_sensitive_attributes(spans: list[object]) -> None:
    for span in spans:
        attrs = getattr(span, "attributes", None) or {}
        for attr_key, attr_val in attrs.items():
            assert "semantic search" not in str(attr_val)
            assert "content" not in str(attr_val)
            assert "query" not in attr_key.lower() or attr_key.startswith("db.")


@pytest.mark.asyncio
async def test_search_produces_trace_with_dependency_spans(
    exporter: InMemorySpanExporter,
) -> None:
    first, second = UUID(int=1), UUID(int=2)
    repo = _build_test_repo([first, second], [0.20, 0.95])

    tracer = get_tracer()
    with (
        tracer.start_as_current_span("test_search_parent") as parent_span,
        patch(
            "app.read.repository.full_text_search",
            AsyncMock(return_value=[FullTextHit(memory_id=second, rank=0.8)]),
        ),
    ):
        results = await repo.find_similar(_query(query_text="semantic search", limit=2))

    assert len(results) == 2
    spans = exporter.get_finished_spans()
    span_names = {s.name for s in spans}

    assert {"vector_search", "rerank", "test_search_parent"}.issubset(span_names)

    parent_trace_id = parent_span.get_span_context().trace_id
    _assert_dependency_spans(spans, parent_trace_id)

    rerank_span = next(s for s in spans if s.name == "rerank")
    assert rerank_span.parent.span_id == parent_span.get_span_context().span_id
    assert rerank_span.attributes["rerank.outcome"] == "applied"
    assert rerank_span.attributes["rerank.endpoint_host"] == "rerank.internal"
    _assert_no_sensitive_attributes(spans)


@pytest.mark.asyncio
async def test_search_rerank_degraded_span(exporter: InMemorySpanExporter) -> None:
    first, second = UUID(int=1), UUID(int=2)
    repo = _build_test_repo([first, second], RerankTimeoutError("timed out"))

    tracer = get_tracer()
    with (
        tracer.start_as_current_span("test_degrade_parent"),
        patch("app.read.repository.full_text_search", AsyncMock(return_value=[])),
    ):
        results = await repo.find_similar(_query(limit=2))

    assert len(results) == 2
    spans = exporter.get_finished_spans()
    rerank_span = next(s for s in spans if s.name == "rerank")
    assert rerank_span.attributes["rerank.outcome"] == "degraded"
    assert rerank_span.attributes["rerank.endpoint_host"] == "rerank.internal"


def test_unconfigured_otlp_starts_unchanged_and_exports_nothing() -> None:
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = configure_tracing("")
    assert provider is not None
    # No BatchSpanProcessor exporting to OTLP was configured
    otlp_processors = [
        p
        for p in getattr(provider._active_span_processor, "_span_processors", [])
        if isinstance(p, BatchSpanProcessor)
    ]
    assert len(otlp_processors) == 0


@pytest.mark.parametrize(
    ("raw_endpoint", "expected_url"),
    [
        ("http://otel-collector:4318", "http://otel-collector:4318/v1/traces"),
        ("http://otel-collector:4318/", "http://otel-collector:4318/v1/traces"),
        ("http://otel-collector:4318/v1/traces", "http://otel-collector:4318/v1/traces"),
        ("http://otel-collector:4318/v1/traces/", "http://otel-collector:4318/v1/traces"),
        ("  http://otel-collector:4318  ", "http://otel-collector:4318/v1/traces"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_traces_endpoint_is_normalized(raw_endpoint: str, expected_url: str) -> None:
    assert _traces_endpoint(raw_endpoint) == expected_url
