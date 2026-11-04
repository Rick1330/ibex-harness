"""OpenTelemetry wiring, context propagation, and dependency spans for the memory service."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import set_global_textmap
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_TRACER_NAME = "ibex.memory"
_DEFAULT_SAMPLE_RATIO = 1.0
_provider: TracerProvider | None = None


def _sample_ratio(sample_ratio: float | None = None) -> float:
    if sample_ratio is not None:
        return max(0.0, min(1.0, sample_ratio))
    raw = os.getenv("OTEL_SAMPLE_RATIO", "").strip()
    if not raw:
        return _DEFAULT_SAMPLE_RATIO
    try:
        ratio = float(raw)
        return max(0.0, min(1.0, ratio))
    except ValueError:
        return _DEFAULT_SAMPLE_RATIO


def _service_name(fallback: str = "ibex-memory") -> str:
    return os.getenv("OTEL_SERVICE_NAME", fallback).strip() or fallback


def _service_version() -> str:
    return os.getenv("OTEL_SERVICE_VERSION", "dev").strip() or "dev"


def _deployment_environment() -> str:
    return (
        os.getenv("OTEL_DEPLOYMENT_ENVIRONMENT")
        or os.getenv("IBEX_ENV")
        or os.getenv("IBEX_MEMORY_ENV")
        or "development"
    ).strip() or "development"


def _traces_endpoint(endpoint: str) -> str:
    """Normalize OTLP traces URL endpoint."""
    cleaned = endpoint.strip().rstrip("/")
    if not cleaned:
        return ""
    return cleaned if cleaned.endswith("/v1/traces") else f"{cleaned}/v1/traces"


def configure_tracing(
    endpoint: str = "",
    *,
    service_name: str | None = None,
    sample_ratio: float | None = None,
) -> TracerProvider:
    """Configure the global tracer provider once for the process.

    If endpoint is empty (the default when OTEL_EXPORTER_OTLP_ENDPOINT is unset),
    tracing context propagation is enabled without exporting spans.
    """
    global _provider
    if _provider is not None:
        return _provider

    name = service_name or _service_name()
    resource = Resource.create(
        {
            "service.name": name,
            "service.version": _service_version(),
            "deployment.environment": _deployment_environment(),
        }
    )
    sampler = ParentBased(root=TraceIdRatioBased(_sample_ratio(sample_ratio)))
    provider = TracerProvider(resource=resource, sampler=sampler)

    effective_endpoint = endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    target = _traces_endpoint(effective_endpoint)
    if target:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=target, timeout=2))
        )

    trace.set_tracer_provider(provider)
    set_global_textmap(TraceContextTextMapPropagator())
    _provider = provider
    return provider


def shutdown_tracing() -> None:
    """Flush the active tracer provider on application shutdown."""
    if _provider is not None:
        _provider.force_flush()


def reset_tracing_for_tests() -> None:
    """Test-only helper to clear provider state."""
    global _provider
    _provider = None


def get_tracer() -> trace.Tracer:
    """Return the memory service tracer."""
    return trace.get_tracer(_TRACER_NAME)


def extract_context(headers: Mapping[str, str]) -> Any:
    """Extract W3C trace context from inbound HTTP headers."""
    return TraceContextTextMapPropagator().extract(dict(headers))


class TracingMiddleware:
    """Server span for incoming HTTP requests continuing W3C trace context."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        raw_headers = scope.get("headers") or []
        header_map = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in raw_headers
        }
        method = str(scope.get("method", "GET"))
        route_path = str(scope.get("path", ""))

        server_span = get_tracer().start_span(
            "memory.http",
            context=extract_context(header_map),
            kind=SpanKind.SERVER,
            attributes={
                "http.request.method": method,
                "url.path": route_path,
            },
        )

        async def intercept_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                server_span.set_attribute(
                    "http.response.status_code", int(message["status"])
                )
            await send(message)

        with trace.use_span(server_span, end_on_exit=False):
            try:
                await self._app(scope, receive, intercept_send)
            except Exception as err:
                server_span.record_exception(err)
                server_span.set_status(Status(StatusCode.ERROR, str(err)))
                raise
            finally:
                server_span.end()
