"""Unit tests for OTel bootstrap."""

from __future__ import annotations

import os

import pytest

from app.telemetry import TRACER_NAME, get_tracer, init_tracing, reset_tracing_for_tests


@pytest.fixture(autouse=True)
def _reset_tracing() -> None:
    reset_tracing_for_tests()
    yield
    reset_tracing_for_tests()


def test_init_tracing_no_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    init_tracing()
    tracer = get_tracer()
    assert tracer is not None
    with tracer.start_as_current_span("test.span"):
        pass


def test_init_tracing_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    init_tracing()
    first = get_tracer()
    init_tracing()
    second = get_tracer()
    assert first is second


def test_init_tracing_with_otlp_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "ibex-worker-test")
    init_tracing()
    with get_tracer().start_as_current_span("otlp.test"):
        pass


def test_sample_ratio_invalid_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_SAMPLE_RATIO", "not-a-number")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    init_tracing()
    assert get_tracer() is not None


def test_tracer_name_constant() -> None:
    assert TRACER_NAME == "ibex-worker"
    assert os.getenv("OTEL_SERVICE_NAME", TRACER_NAME)
