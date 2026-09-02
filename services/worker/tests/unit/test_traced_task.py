"""Unit tests for run_task_in_span / traced_task OTel spans."""

from __future__ import annotations

import pytest
from celery.exceptions import Retry
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.observability import run_task_in_span, traced_task
from app.telemetry import TRACER_NAME, reset_tracing_for_tests


@pytest.fixture(autouse=True)
def otel_memory_exporter(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    reset_tracing_for_tests()
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer(TRACER_NAME)
    monkeypatch.setattr("app.observability.get_tracer", lambda: tracer)
    yield exporter
    exporter.clear()
    reset_tracing_for_tests()


def test_run_task_in_span_success(otel_memory_exporter: InMemorySpanExporter) -> None:
    result = run_task_in_span(
        "ibex.worker.test.ok",
        "task-1",
        {"org_id": "550e8400-e29b-41d4-a716-446655440000"},
        lambda: 42,
    )
    assert result == 42
    spans = otel_memory_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "ibex.worker.test.ok"
    assert span.status.is_ok
    attrs = dict(span.attributes or {})
    assert attrs["worker.task"] == "ibex.worker.test.ok"
    assert attrs["celery.task_id"] == "task-1"
    assert attrs["ibex.org_id"] == "550e8400-e29b-41d4-a716-446655440000"


def test_run_task_in_span_failure_records_exception(
    otel_memory_exporter: InMemorySpanExporter,
) -> None:
    with pytest.raises(ValueError, match="boom"):
        run_task_in_span(
            "ibex.worker.test.fail",
            None,
            {},
            lambda: (_ for _ in ()).throw(ValueError("boom")),
        )
    spans = otel_memory_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert not span.status.is_ok
    assert any(event.name == "exception" for event in span.events)


def test_traced_task_decorator(otel_memory_exporter: InMemorySpanExporter) -> None:
    @traced_task("decorated.task")
    def sample() -> str:
        return "done"

    assert sample() == "done"
    spans = otel_memory_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "decorated.task"


def test_run_task_in_span_propagates_retry_without_error_status(
    otel_memory_exporter: InMemorySpanExporter,
) -> None:
    with pytest.raises(Retry):
        run_task_in_span(
            "ibex.worker.test.retry",
            "task-retry",
            {},
            lambda: (_ for _ in ()).throw(Retry("retrying")),
        )
    spans = otel_memory_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.status.is_ok
    assert not any(event.name == "exception" for event in span.events)
