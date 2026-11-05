"""OpenTelemetry outbound propagation tests for the memory HTTP clients."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
import respx
from httpx import Response as HTTPXResponse
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.clients.embedding import EmbeddingClient, EmbeddingClientConfig
from app.clients.rerank import RerankClient, RerankClientConfig
from app.tracing import start_span
from tests.unit.tracing_support import _clear_spans, _only_span, exporter

# Keep the imported fixtures referenced so ruff does not treat them as unused;
# pytest resolves them from the module namespace.
_TRACING_FIXTURES = (exporter, _clear_spans)

pytestmark = pytest.mark.usefixtures("exporter")


# ---------------------------------------------------------------------------
# 9: outbound propagation from both HTTP clients
# ---------------------------------------------------------------------------


def _embed_body() -> dict[str, Any]:
    return {
        "vectors": [[0.0] * 1024],
        "model_id": "bge-m3",
        "dimensions": 1024,
        "backend": "tei",
    }


@pytest.mark.asyncio
@respx.mock
async def test_outbound_clients_forward_w3c_trace_context(
    exporter: InMemorySpanExporter,
) -> None:
    captured: dict[str, str | None] = {}

    def capture_embed(request: Any) -> HTTPXResponse:
        captured["embed"] = request.headers.get("traceparent")
        return HTTPXResponse(200, json=_embed_body())

    def capture_rerank(request: Any) -> HTTPXResponse:
        captured["rerank"] = request.headers.get("traceparent")
        return HTTPXResponse(200, json=[{"index": 0, "score": 0.9}])

    respx.post("https://embedder.test/v1/embed").mock(side_effect=capture_embed)
    respx.post("https://rerank.test/rerank").mock(side_effect=capture_rerank)
    embedding = EmbeddingClient(
        "https://embedder.test",
        "test-token",
        config=EmbeddingClientConfig(max_retries=0),
    )
    rerank = RerankClient(
        "https://rerank.test",
        config=RerankClientConfig(max_retries=0),
    )
    try:
        with start_span("test_outbound_parent") as parent:
            await embedding.embed(["hello"], org_id=uuid4())
            await rerank.rerank("query", ["document"])
        expected_trace_id = format(parent.get_span_context().trace_id, "032x")
    finally:
        await embedding.aclose()
        await rerank.aclose()

    assert set(captured) == {"embed", "rerank"}
    embed_span = _only_span(exporter, "embedder.embed")

    def _parts(header: str | None) -> tuple[str, str, str]:
        assert header is not None
        version, trace_id, span_id, _flags = header.split("-")
        return version, trace_id, span_id

    # EmbeddingClient wraps the call in its own span, so the header names that span.
    version, trace_id, span_id = _parts(captured["embed"])
    assert version == "00"
    assert trace_id == expected_trace_id
    assert span_id == format(embed_span.context.span_id, "016x")

    # RerankClient makes the request directly; the repository owns the rerank span.
    version, trace_id, span_id = _parts(captured["rerank"])
    assert version == "00"
    assert trace_id == expected_trace_id
    assert span_id == format(parent.get_span_context().span_id, "016x")
