"""OpenTelemetry provider configuration, endpoint, and sampling tests for memory."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
from opentelemetry.sdk.trace.sampling import Decision, TraceIdRatioBased

from app import tracing
from app.config import Settings
from app.db import create_engine
from app.tracing import (
    _EXPORTER_LOGGER,
    _RedactEndpointFilter,
    _traces_endpoint,
    configure_tracing,
    get_tracer,
    reset_tracing_for_tests,
    shutdown_tracing,
)
from tests.unit.tracing_support import isolated_provider

# Keep the imported fixture referenced so ruff does not treat it as unused;
# pytest resolves it from the module namespace.
_TRACING_FIXTURES = (isolated_provider,)

# ---------------------------------------------------------------------------
# 10: endpoint handling
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw_endpoint", "expected_url"),
    [
        ("http://otel-collector:4318", "http://otel-collector:4318/v1/traces"),
        ("http://otel-collector:4318/", "http://otel-collector:4318/v1/traces"),
        ("http://otel-collector:4318/v1/traces", "http://otel-collector:4318/v1/traces"),
        ("http://otel-collector:4318/v1/traces/", "http://otel-collector:4318/v1/traces"),
        ("  http://otel-collector:4318  ", "http://otel-collector:4318/v1/traces"),
        (
            "https://c.example?tenant=memory",
            "https://c.example/v1/traces?tenant=memory",
        ),
        ("", ""),
        ("   ", ""),
        ("grpc://collector:4317", ""),
        ("ftp://collector/v1/traces", ""),
        ("http://", ""),
        ("http://[::1]:4318", "http://[::1]:4318/v1/traces"),
        ("http://[::1", ""),
        ("http://collector:not-a-port", ""),
        ("http://collector:99999999", ""),
        ("https://c.example/v1/traces#frag", "https://c.example/v1/traces#frag"),
    ],
)
def test_traces_endpoint_is_normalized(raw_endpoint: str, expected_url: str) -> None:
    assert _traces_endpoint(raw_endpoint) == expected_url


def test_unconfigured_endpoint_adds_no_exporter(
    isolated_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    exporter_cls = MagicMock()
    monkeypatch.setattr(tracing, "OTLPSpanExporter", exporter_cls)

    configure_tracing("")

    exporter_cls.assert_not_called()


def test_explicit_empty_endpoint_does_not_read_environment(
    isolated_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
    exporter_cls = MagicMock()
    monkeypatch.setattr(tracing, "OTLPSpanExporter", exporter_cls)

    configure_tracing("")

    exporter_cls.assert_not_called()


def test_none_endpoint_reads_environment(
    isolated_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://c.example?tenant=memory")
    exporter_cls = MagicMock()
    processor_cls = MagicMock()
    monkeypatch.setattr(tracing, "OTLPSpanExporter", exporter_cls)
    monkeypatch.setattr(tracing, "BatchSpanProcessor", processor_cls)

    configure_tracing(None)

    exporter_cls.assert_called_once_with(
        endpoint="https://c.example/v1/traces?tenant=memory",
        timeout=2,
    )
    processor_cls.assert_called_once_with(exporter_cls.return_value)


def test_non_http_endpoint_adds_no_exporter(
    isolated_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    exporter_cls = MagicMock()
    monkeypatch.setattr(tracing, "OTLPSpanExporter", exporter_cls)

    configure_tracing("grpc://collector:4317")

    exporter_cls.assert_not_called()


# ---------------------------------------------------------------------------
# 11: sampling
# ---------------------------------------------------------------------------


def test_default_sample_ratio_drops_root_span(
    isolated_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OTEL_SAMPLE_RATIO", raising=False)
    provider = configure_tracing("")

    decision = provider.sampler.should_sample(None, TraceIdRatioBased.TRACE_ID_LIMIT, "root")

    assert decision.decision is Decision.DROP


def test_sample_ratio_environment_overrides_default(
    isolated_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_SAMPLE_RATIO", "1.0")
    provider = configure_tracing("")

    decision = provider.sampler.should_sample(None, TraceIdRatioBased.TRACE_ID_LIMIT, "root")

    assert decision.decision is Decision.RECORD_AND_SAMPLE


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", 0.01),
        ("not-a-number", 0.01),
        ("-0.5", 0.01),
        ("1.5", 0.01),
        ("nan", 0.01),
        ("0.25", 0.25),
        ("0.0", 0.0),
        ("1.0", 1.0),
    ],
)
def test_sample_ratio_parsing(raw: str, expected: float, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_SAMPLE_RATIO", raw)
    assert tracing._sample_ratio() == expected


def test_explicit_sample_ratio_is_validated() -> None:
    assert tracing._sample_ratio(0.5) == 0.5
    assert tracing._sample_ratio(0.0) == 0.0
    assert tracing._sample_ratio(2.0) == 0.01
    assert tracing._sample_ratio(float("inf")) == 0.01


def test_traces_sampler_environment_logs_one_warning(
    isolated_provider: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("OTEL_TRACES_SAMPLER", "always_on")
    with caplog.at_level(logging.WARNING, logger="app.tracing"):
        configure_tracing("")

    warnings = [
        record
        for record in caplog.records
        if "OTEL_SAMPLE_RATIO is authoritative" in record.getMessage()
    ]
    assert len(warnings) == 1
    assert "always_on" in warnings[0].getMessage()


def test_configure_tracing_is_idempotent(isolated_provider: None) -> None:
    first = configure_tracing("")
    assert configure_tracing("") is first


def test_get_tracer_binds_to_configured_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = MagicMock()
    sentinel_tracer = object()
    provider.get_tracer.return_value = sentinel_tracer
    monkeypatch.setattr(tracing, "_provider", provider)

    assert get_tracer() is sentinel_tracer
    provider.get_tracer.assert_called_once_with("ibex.memory")


def test_reset_tracing_detaches_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tracing, "_provider", MagicMock())

    reset_tracing_for_tests()

    assert tracing._provider is None


def test_resource_attribute_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_SERVICE_NAME", "explicit-service")
    assert tracing._service_name() == "explicit-service"

    monkeypatch.delenv("OTEL_SERVICE_NAME")
    monkeypatch.setenv("IBEX_SERVICE_NAME", "ibex-service")
    assert tracing._service_name() == "ibex-service"

    monkeypatch.delenv("IBEX_SERVICE_NAME")
    assert tracing._service_name() == "ibex-memory"

    monkeypatch.setenv("OTEL_SERVICE_VERSION", "1.2.3")
    assert tracing._service_version() == "1.2.3"
    monkeypatch.setenv("OTEL_SERVICE_VERSION", "  ")
    assert tracing._service_version() == "dev"

    monkeypatch.setenv("OTEL_DEPLOYMENT_ENVIRONMENT", "staging")
    assert tracing._deployment_environment() == "staging"
    monkeypatch.delenv("OTEL_DEPLOYMENT_ENVIRONMENT")
    monkeypatch.setenv("IBEX_ENV", "ci")
    assert tracing._deployment_environment() == "ci"
    monkeypatch.delenv("IBEX_ENV")
    monkeypatch.setenv("IBEX_MEMORY_ENV", "memory-ci")
    assert tracing._deployment_environment() == "memory-ci"
    monkeypatch.delenv("IBEX_MEMORY_ENV")
    assert tracing._deployment_environment() == "development"


# ---------------------------------------------------------------------------
# 12: shutdown
# ---------------------------------------------------------------------------


def test_shutdown_flushes_and_detaches(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = MagicMock()
    monkeypatch.setattr(tracing, "_provider", provider)
    sentinel_tracer = object()
    monkeypatch.setattr(tracing.trace, "get_tracer", MagicMock(return_value=sentinel_tracer))

    shutdown_tracing()

    provider.force_flush.assert_called_once_with()
    provider.shutdown.assert_called_once_with()
    assert tracing._provider is None
    # The detached module falls back to the global accessor (the no-op proxy).
    assert get_tracer() is sentinel_tracer


def test_shutdown_without_provider_is_a_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tracing, "_provider", None)
    shutdown_tracing()
    assert tracing._provider is None


# ---------------------------------------------------------------------------
# Exporter log redaction
# ---------------------------------------------------------------------------


def test_exporter_failure_log_redacts_endpoint_credentials() -> None:
    record = logging.LogRecord(
        _EXPORTER_LOGGER,
        logging.WARNING,
        __file__,
        1,
        "Transient error HTTPConnectionPool(host='c', port=4318): Max retries exceeded with "
        "url: /v1/traces?api_key=%s (Caused by NewConnectionError())",
        ("SENTINEL-API-KEY",),
        None,
    )
    assert _RedactEndpointFilter().filter(record) is True
    message = record.getMessage()
    assert "SENTINEL-API-KEY" not in message
    assert "?<redacted>" in message

    userinfo = logging.LogRecord(
        _EXPORTER_LOGGER,
        logging.WARNING,
        __file__,
        1,
        "posting to http://operator:SENTINEL-PASSWORD@collector:4318/v1/traces",
        (),
        None,
    )
    assert _RedactEndpointFilter().filter(userinfo) is True
    assert "SENTINEL-PASSWORD" not in userinfo.getMessage()


def test_configure_tracing_installs_log_redaction(isolated_provider: None) -> None:
    configure_tracing("")
    filters = logging.getLogger(_EXPORTER_LOGGER).filters
    assert any(isinstance(item, _RedactEndpointFilter) for item in filters)


# ---------------------------------------------------------------------------
# Defence in depth: bound parameters stay out of SQLAlchemy error text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_hides_bound_parameters() -> None:
    engine = create_engine(Settings(database_url="postgresql+asyncpg://u:p@localhost/db"))
    try:
        assert engine.sync_engine.hide_parameters is True
    finally:
        await engine.dispose()
