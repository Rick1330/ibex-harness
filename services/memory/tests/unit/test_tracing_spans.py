"""OpenTelemetry dependency-span tests for the memory read path."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import StatementError

from app.clients.rerank import RerankTimeoutError
from app.read.full_text import FullTextSearchQuery, full_text_search
from app.read.hot_cache import MemoryHotCacheReader
from app.read.models import HotMemoryQuery
from app.tracing import TracingMiddleware, get_tracer, start_span
from tests.unit.tracing_support import (
    _RERANK_ATTRIBUTE_ALLOWLIST,
    _SENTINEL,
    _build_repository,
    _clear_spans,
    _FakeRerankClient,
    _mapping_result,
    _only_span,
    _search_query,
    _session_factory,
    exporter,
)

# Keep the imported fixtures referenced so ruff does not treat them as unused;
# pytest resolves them from the module namespace.
_TRACING_FIXTURES = (exporter, _clear_spans)

pytestmark = pytest.mark.usefixtures("exporter")


# ---------------------------------------------------------------------------
# 1-3: dependency spans on the real read path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_trace_covers_the_four_dependency_spans(
    exporter: InMemorySpanExporter,
) -> None:
    first, second = UUID(int=1), UUID(int=2)
    repository = _build_repository(
        ids=[first, second],
        fts_ids=[second],
        contents={first: "alpha content", second: "beta content"},
        rerank_client=_FakeRerankClient(scores=[0.2, 0.95]),
    )

    with get_tracer().start_as_current_span("test_search_parent") as parent:
        results = await repository.find_similar(_search_query())

    assert len(results) == 2
    parent_context = parent.get_span_context()
    spans = {span.name: span for span in exporter.get_finished_spans()}
    assert {"vector_search", "full_text_search", "hydration", "rerank"} <= set(spans)
    for name in ("vector_search", "full_text_search", "hydration", "rerank"):
        assert spans[name].context.trace_id == parent_context.trace_id
        assert spans[name].parent.span_id == parent_context.span_id
    assert dict(spans["vector_search"].attributes) == {
        "db.system": "postgresql",
        "search.mode": "user_retrieval",
    }
    assert dict(spans["full_text_search"].attributes) == {
        "db.system": "postgresql",
        "db.operation": "full_text_search",
    }
    assert dict(spans["hydration"].attributes) == {
        "db.system": "postgresql",
        "db.operation": "hydrate",
        "memory.candidate_count": 2,
    }
    assert dict(spans["rerank"].attributes) == {
        "server.address": "rerank.internal",
        "rerank.endpoint_host": "rerank.internal",
        "rerank.outcome": "applied",
    }


def test_dependency_spans_are_children_of_the_http_span(
    exporter: InMemorySpanExporter,
) -> None:
    """A real request must make ``memory.http`` the parent of the search spans."""
    first, second = UUID(int=1), UUID(int=2)
    repository = _build_repository(
        ids=[first, second],
        fts_ids=[second],
        contents={first: "alpha content", second: "beta content"},
        rerank_client=_FakeRerankClient(scores=[0.2, 0.95]),
    )
    application = FastAPI()
    application.add_middleware(TracingMiddleware)

    @application.get("/v1/memories/{memory_id}/search")
    async def search(memory_id: str) -> dict[str, int]:
        return {"count": len(await repository.find_similar(_search_query()))}

    with TestClient(application) as client:
        assert client.get(f"/v1/memories/{uuid4()}/search").status_code == 200

    http_span = _only_span(exporter, "memory.http")
    for name in ("vector_search", "full_text_search", "hydration", "rerank"):
        span = _only_span(exporter, name)
        assert span.context.trace_id == http_span.context.trace_id
        assert span.parent.span_id == http_span.context.span_id
    assert http_span.attributes["http.route"] == "/v1/memories/{memory_id}/search"


@pytest.mark.asyncio
async def test_rerank_span_carries_no_query_or_document_text(
    exporter: InMemorySpanExporter,
) -> None:
    first, second = UUID(int=1), UUID(int=2)
    documents = {first: "first secret document", second: "second secret document"}
    repository = _build_repository(
        ids=[first, second],
        fts_ids=[second],
        contents=documents,
        rerank_client=_FakeRerankClient(scores=[0.2, 0.95]),
    )

    with get_tracer().start_as_current_span("test_search_parent"):
        await repository.find_similar(_search_query())

    span = _only_span(exporter, "rerank")
    assert span.events == ()
    assert set(span.attributes) <= _RERANK_ATTRIBUTE_ALLOWLIST
    rendered = repr(dict(span.attributes))
    for value in span.attributes.values():
        assert "semantic search" not in str(value)
        assert "secret document" not in str(value)
        assert _SENTINEL not in str(value)
    assert "semantic search" not in rendered


@pytest.mark.asyncio
async def test_rerank_degraded_path_keeps_span_successful(
    exporter: InMemorySpanExporter,
) -> None:
    first, second = UUID(int=1), UUID(int=2)
    repository = _build_repository(
        ids=[first, second],
        fts_ids=[second],
        contents={first: "alpha", second: "beta"},
        rerank_client=_FakeRerankClient(error=RerankTimeoutError("timed out")),
    )

    with get_tracer().start_as_current_span("test_degrade_parent"):
        results = await repository.find_similar(_search_query())

    assert len(results) == 2
    span = _only_span(exporter, "rerank")
    assert span.attributes["rerank.outcome"] == "degraded"
    assert span.status.status_code is StatusCode.UNSET
    assert span.events == ()


@pytest.mark.asyncio
async def test_rerank_span_tolerates_a_client_without_a_host(
    exporter: InMemorySpanExporter,
) -> None:
    """Integration fakes implement ``rerank`` only; the span must not carry a mock."""

    class _HostlessReranker:
        async def rerank(self, _query: str, documents: list[str]) -> list[float]:
            return [0.9 for _ in documents]

    first, second = UUID(int=1), UUID(int=2)
    repository = _build_repository(
        ids=[first, second],
        fts_ids=[second],
        contents={first: "alpha", second: "beta"},
        rerank_client=_HostlessReranker(),  # type: ignore[arg-type]
    )

    with get_tracer().start_as_current_span("test_hostless_parent"):
        assert len(await repository.find_similar(_search_query())) == 2

    span = _only_span(exporter, "rerank")
    assert span.attributes["server.address"] == ""
    assert span.attributes["rerank.endpoint_host"] == ""
    assert span.attributes["rerank.outcome"] == "applied"


# ---------------------------------------------------------------------------
# 4: a failed statement leaks nothing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_full_text_statement_leaks_no_query_text(
    exporter: InMemorySpanExporter,
) -> None:
    def _statement_error() -> StatementError:
        return StatementError(
            f"full-text query failed for {_SENTINEL}",
            str(text("SELECT 1")),
            {"query_text": _SENTINEL},
            RuntimeError(_SENTINEL),
        )

    async def execute(statement: Any, params: dict[str, Any] | None = None) -> MagicMock:
        if "ts_rank_cd" in str(statement):
            raise _statement_error()
        return _mapping_result([])

    query = FullTextSearchQuery(
        org_id=uuid4(),
        agent_id=uuid4(),
        query_text=_SENTINEL,
        limit=5,
        min_confidence=0.0,
    )
    factory = _session_factory(execute)
    with pytest.raises(StatementError) as raised:
        await full_text_search(factory, query)

    # The exception text itself would have carried the bound parameter, which is
    # exactly what the span policy must not copy.
    assert _SENTINEL in str(raised.value)

    span = _only_span(exporter, "full_text_search")
    assert span.events == ()
    assert span.status.status_code is StatusCode.ERROR
    # Policy (spec §1.1): the description is the exception class name, never
    # str(exc). (Spec §5.4 says None; §1.1's class-name rule is the decided one.)
    assert span.status.description == "StatementError"
    assert _SENTINEL not in repr(dict(span.attributes))
    assert _SENTINEL not in repr(span.events)
    assert _SENTINEL not in (span.status.description or "")


# ---------------------------------------------------------------------------
# 8: Redis read failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_failure_sets_error_and_returns_empty(
    exporter: InMemorySpanExporter,
) -> None:
    redis = AsyncMock()
    redis.zrevrange = AsyncMock(side_effect=RedisError("down"))
    reader = MemoryHotCacheReader(redis, MagicMock())

    results = await reader.get_hot_memories(
        HotMemoryQuery(org_id=uuid4(), agent_id=uuid4(), limit=5)
    )

    assert results == []
    span = _only_span(exporter, "redis.read_hot")
    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description == "RedisError"
    assert span.events == ()


# ---------------------------------------------------------------------------
# start_span defaults
# ---------------------------------------------------------------------------


def test_start_span_defaults_to_internal_kind(exporter: InMemorySpanExporter) -> None:
    with start_span("probe"):
        pass
    span = _only_span(exporter, "probe")
    assert span.kind is SpanKind.INTERNAL
