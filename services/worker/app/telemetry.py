"""OpenTelemetry bootstrap for the Celery worker (ADR-0019 Python mirror)."""

from __future__ import annotations

import os
from functools import lru_cache

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

TRACER_NAME = "ibex-worker"

_DEFAULT_SAMPLE_RATIO = 0.01
_initialized = False


def _sample_ratio() -> float:
    raw = os.getenv("OTEL_SAMPLE_RATIO", str(_DEFAULT_SAMPLE_RATIO)).strip()
    try:
        ratio = float(raw)
    except ValueError:
        return _DEFAULT_SAMPLE_RATIO
    if ratio < 0.0 or ratio > 1.0:
        return _DEFAULT_SAMPLE_RATIO
    return ratio


def _service_name() -> str:
    return os.getenv("OTEL_SERVICE_NAME", TRACER_NAME).strip() or TRACER_NAME


def _service_version() -> str:
    return os.getenv("OTEL_SERVICE_VERSION", "dev").strip() or "dev"


def _deployment_environment() -> str:
    return (
        os.getenv("OTEL_DEPLOYMENT_ENVIRONMENT")
        or os.getenv("IBEX_ENV")
        or os.getenv("IBEX_WORKER_ENV")
        or "development"
    ).strip() or "development"


@lru_cache
def get_tracer() -> trace.Tracer:
    return trace.get_tracer(TRACER_NAME)


def init_tracing() -> None:
    """Configure global TracerProvider once per worker process."""
    global _initialized
    if _initialized:
        return

    resource = Resource.create(
        {
            "service.name": _service_name(),
            "service.version": _service_version(),
            "deployment.environment": _deployment_environment(),
        }
    )
    sampler = ParentBased(root=TraceIdRatioBased(_sample_ratio()))
    provider = TracerProvider(resource=resource, sampler=sampler)

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if endpoint:
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    from opentelemetry import propagate

    propagate.set_global_textmap(TraceContextTextMapPropagator())
    _initialized = True


def reset_tracing_for_tests() -> None:
    """Test-only reset of provider state."""
    global _initialized
    _initialized = False
    if hasattr(get_tracer, "cache_clear"):
        get_tracer.cache_clear()
