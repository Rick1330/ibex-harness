"""Shared fixtures and helpers for the memory OpenTelemetry tracing tests."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app import tracing
from app.read.repository import MemoryReadRepository
from app.tracing import configure_tracing, reset_tracing_for_tests, shutdown_tracing
from app.vectorstore.base import SearchHit
from tests.unit.find_similar_support import make_query, make_settings

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
SPAN_ID = "00f067aa0ba902b7"
_SENTINEL = "SENTINEL-QUERY-TEXT-DO-NOT-LEAK"
_RERANK_ATTRIBUTE_ALLOWLIST = {"server.address", "rerank.endpoint_host", "rerank.outcome"}
_NOW = datetime.now(tz=UTC)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def exporter() -> Iterator[InMemorySpanExporter]:
    """One configured provider for the module, with an in-memory span sink."""
    reset_tracing_for_tests()
    sink = InMemorySpanExporter()
    provider = configure_tracing("", sample_ratio=1.0)
    provider.add_span_processor(SimpleSpanProcessor(sink))
    yield sink
    shutdown_tracing()


@pytest.fixture(autouse=True)
def _clear_spans(exporter: InMemorySpanExporter) -> None:
    exporter.clear()


@pytest.fixture
def isolated_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let one test build its own provider; monkeypatch restores it afterwards."""
    monkeypatch.setattr(tracing, "_provider", None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _only_span(exporter: InMemorySpanExporter, name: str) -> Any:
    spans = [span for span in exporter.get_finished_spans() if span.name == name]
    assert len(spans) == 1, f"expected one {name!r} span, got {[s.name for s in spans]}"
    return spans[0]


def _mapping_result(rows: list[dict[str, Any]]) -> MagicMock:
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    return result


def _session_factory(execute: Any) -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=execute)
    begin = MagicMock()
    begin.__aenter__ = AsyncMock(return_value=None)
    begin.__aexit__ = AsyncMock(return_value=None)
    session.begin = MagicMock(return_value=begin)
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


def _hydrate_row(memory_id: UUID, org_id: UUID, agent_id: UUID, content: str) -> dict[str, Any]:
    return {
        "id": memory_id,
        "org_id": org_id,
        "agent_id": agent_id,
        "content": content,
        "category": "factual",
        "confidence": 0.9,
        "status": "active",
        "created_at": _NOW,
        "updated_at": _NOW,
        "valid_from": _NOW - timedelta(days=1),
        "usefulness_score": 0.5,
        "retrieval_count": 0,
        "lifecycle_revision": 1,
        "categories": ["factual"],
        "conflict_groups": [],
    }


class _FakeRerankClient:
    """Structural stand-in for ``RerankClient``: one attribute, one coroutine."""

    def __init__(
        self,
        *,
        host: str = "rerank.internal",
        scores: list[float] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.host = host
        self._scores = scores or []
        self._error = error

    async def rerank(self, _query: str, documents: list[str]) -> list[float]:
        if self._error is not None:
            raise self._error
        return self._scores[: len(documents)]


def _fake_executor(
    fts_rows: list[dict[str, Any]],
    rows_by_id: dict[UUID, dict[str, Any]],
) -> Any:
    """Async ``session.execute`` stand-in serving full-text and hydration queries."""

    async def execute(statement: Any, params: dict[str, Any] | None = None) -> MagicMock:
        if "ts_rank_cd" in str(statement):
            return _mapping_result(fts_rows)
        if not params or "memory_ids" not in params:
            return _mapping_result([])
        requested = [UUID(str(memory_id)) for memory_id in params["memory_ids"]]
        return _mapping_result([rows_by_id[item] for item in requested if item in rows_by_id])

    return execute


def _build_repository(
    *,
    ids: list[UUID],
    fts_ids: list[UUID],
    contents: dict[UUID, str],
    rerank_client: _FakeRerankClient,
) -> MemoryReadRepository:
    """Hybrid repository whose real ``full_text_search`` and ``_hydrate_hits`` run."""
    org_id = uuid4()
    agent_id = uuid4()
    rows_by_id = {
        memory_id: _hydrate_row(memory_id, org_id, agent_id, contents[memory_id])
        for memory_id in ids
    }
    fts_rows = [{"memory_id": str(memory_id), "rank": 0.8} for memory_id in fts_ids]

    store = MagicMock()
    store.search = AsyncMock(
        return_value=[SearchHit(memory_id=memory_id, similarity=0.9) for memory_id in ids]
    )
    settings = make_settings(search_hybrid_enabled=True, rerank_enabled=True)
    return MemoryReadRepository(
        _session_factory(_fake_executor(fts_rows, rows_by_id)),
        store,
        settings,
        rerank_client=rerank_client,  # type: ignore[arg-type]
    )


def _search_query() -> Any:
    return make_query(query_text="semantic search", limit=2)
