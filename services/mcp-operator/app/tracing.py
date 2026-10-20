"""OpenTelemetry wiring and dependency spans for the operator service."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import set_global_textmap
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_TRACER_NAME = "ibex.mcp_operator"
_provider: TracerProvider | None = None


def configure_tracing(endpoint: str, *, service_name: str = "mcp-operator") -> TracerProvider:
    global _provider
    if _provider is not None:
        return _provider
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    if endpoint.strip():
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint.strip(), timeout=2))
        )
    trace.set_tracer_provider(provider)
    set_global_textmap(TraceContextTextMapPropagator())
    _provider = provider
    return provider


def shutdown_tracing() -> None:
    # The OpenTelemetry global tracer provider cannot be replaced after shutdown,
    # so flush rather than shutdown. Tests and app factories may recreate the
    # application in one process while the provider stays valid.
    if _provider is not None:
        _provider.force_flush()


def get_tracer() -> trace.Tracer:
    return trace.get_tracer(_TRACER_NAME)


def extract_context(headers: Mapping[str, str]) -> Any:
    return TraceContextTextMapPropagator().extract(dict(headers))


class TracingMiddleware:
    """Server span that continues an incoming W3C trace context."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {
            key.decode("latin-1"): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        span = get_tracer().start_span(
            "mcp.http",
            context=extract_context(headers),
            kind=SpanKind.SERVER,
            attributes={
                "http.request.method": str(scope.get("method", "GET")),
                "url.path": str(scope.get("path", "")),
            },
        )

        async def send_with_status(message: Message) -> None:
            if message["type"] == "http.response.start":
                span.set_attribute("http.response.status_code", int(message["status"]))
            await send(message)

        try:
            with trace.use_span(span, end_on_exit=False):
                await self.app(scope, receive, send_with_status)
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR))
            raise
        finally:
            span.end()
