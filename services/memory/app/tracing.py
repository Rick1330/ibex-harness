"""OpenTelemetry wiring, context propagation, and dependency spans for the memory service."""

from __future__ import annotations

import logging
import math
import os
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import set_global_textmap
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Span, SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.http_metrics import http_method, instrument_scope, route_template

logger = logging.getLogger(__name__)

_TRACER_NAME = "ibex.memory"
_DEFAULT_SAMPLE_RATIO = 0.01
_DEFAULT_SERVICE_NAME = "ibex-memory"
_provider: TracerProvider | None = None


def _valid_ratio(ratio: float) -> float:
    """Return ``ratio`` when it is a usable probability, otherwise the default."""
    if not math.isfinite(ratio):
        return _DEFAULT_SAMPLE_RATIO
    if ratio < 0.0:
        return _DEFAULT_SAMPLE_RATIO
    if ratio > 1.0:
        return _DEFAULT_SAMPLE_RATIO
    return ratio


def _sample_ratio(sample_ratio: float | None = None) -> float:
    if sample_ratio is not None:
        return _valid_ratio(sample_ratio)
    raw = os.getenv("OTEL_SAMPLE_RATIO", "").strip()
    if not raw:
        return _DEFAULT_SAMPLE_RATIO
    try:
        ratio = float(raw)
    except ValueError:
        return _DEFAULT_SAMPLE_RATIO
    return _valid_ratio(ratio)


def _warn_on_unused_sampler_env() -> None:
    """One warning when an operator set a sampler variable the SDK cannot honour."""
    sampler = os.getenv("OTEL_TRACES_SAMPLER", "").strip()
    if sampler:
        logger.warning(
            "OTEL_TRACES_SAMPLER=%s is ignored by the memory service; "
            "OTEL_SAMPLE_RATIO is authoritative",
            sampler,
        )


_URL_QUERY = re.compile(r"\?[^\s'\"()]++")
_URL_USERINFO = re.compile(r"//[^/\s@]+@")


class _RedactEndpointFilter(logging.Filter):
    """Strip query strings and userinfo from OTLP exporter failures.

    The exporter logs the request URL when a flush fails. An operator who puts a
    credential in ``OTEL_EXPORTER_OTLP_ENDPOINT`` would otherwise write it to the
    service log. Credentials belong in ``OTEL_EXPORTER_OTLP_HEADERS``; this filter
    makes the mistake harmless.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = _URL_USERINFO.sub("//<redacted>@", message)
        redacted = _URL_QUERY.sub("?<redacted>", redacted)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


_EXPORTER_LOGGER = "opentelemetry.exporter.otlp.proto.http.trace_exporter"


def _install_log_redaction() -> None:
    exporter_logger = logging.getLogger(_EXPORTER_LOGGER)
    if not any(isinstance(item, _RedactEndpointFilter) for item in exporter_logger.filters):
        exporter_logger.addFilter(_RedactEndpointFilter())


def _service_name(fallback: str = _DEFAULT_SERVICE_NAME) -> str:
    return (
        os.getenv("OTEL_SERVICE_NAME") or os.getenv("IBEX_SERVICE_NAME") or fallback
    ).strip() or fallback


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
    """Normalize an OTLP traces URL, changing only the path.

    Query and fragment survive: ``https://c.example?tenant=memory`` becomes
    ``https://c.example/v1/traces?tenant=memory``. An empty value, a scheme other
    than ``http``/``https``, a missing host, or a malformed authority (truncated
    IPv6 literal, non-numeric or out-of-range port) returns ``""`` so no exporter
    is built rather than a bad endpoint taking startup down with it.
    """
    cleaned = endpoint.strip()
    if not cleaned:
        return ""
    try:
        parts = urlsplit(cleaned)
        parts.port  # noqa: B018 - raises ValueError on a malformed authority
    except ValueError:
        return ""
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return ""
    path = parts.path.rstrip("/")
    if not path.endswith("/v1/traces"):
        path = f"{path}/v1/traces"
    return urlunsplit(parts._replace(path=path))


def configure_tracing(
    endpoint: str | None = None,
    *,
    service_name: str | None = None,
    sample_ratio: float | None = None,
) -> TracerProvider:
    """Configure the global tracer provider once for the process.

    ``endpoint=None`` reads ``OTEL_EXPORTER_OTLP_ENDPOINT``; ``endpoint=""``
    explicitly disables export while keeping context propagation. Spans are
    recorded either way, so in-process tests can still assert on them.
    """
    global _provider
    if _provider is not None:
        return _provider

    _warn_on_unused_sampler_env()
    _install_log_redaction()
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

    effective_endpoint = (
        os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "") if endpoint is None else endpoint
    )
    target = _traces_endpoint(effective_endpoint)
    if target:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=target, timeout=2))
        )
    elif effective_endpoint.strip():
        # Do not log the value: it can carry userinfo or a query credential.
        logger.warning(
            "OTEL_EXPORTER_OTLP_ENDPOINT is set but is not a usable http(s) URL; "
            "span export is disabled (value redacted)"
        )

    trace.set_tracer_provider(provider)
    set_global_textmap(TraceContextTextMapPropagator())
    _provider = provider
    return provider


def shutdown_tracing() -> None:
    """Flush and shut the active tracer provider down, then detach it."""
    global _provider
    provider = _provider
    if provider is None:
        return
    provider.force_flush()
    provider.shutdown()
    _provider = None


def reset_tracing_for_tests() -> None:
    """Test-only helper to clear provider state without flushing."""
    global _provider
    _provider = None


def get_tracer() -> trace.Tracer:
    """Return the memory service tracer, bound to the configured provider."""
    if _provider is not None:
        return _provider.get_tracer(_TRACER_NAME)
    return trace.get_tracer(_TRACER_NAME)


@contextmanager
def start_span(
    name: str,
    *,
    attributes: Mapping[str, Any] | None = None,
    kind: SpanKind = SpanKind.INTERNAL,
) -> Iterator[Span]:
    """Start a span that never records exception detail.

    OpenTelemetry stores ``str(exception)`` as the ``exception.message`` event, and
    SQLAlchemy puts bound parameters into ``DBAPIError.__str__``. The status
    description is therefore the exception class name only, and no span event is
    ever written.
    """
    with get_tracer().start_as_current_span(
        name,
        kind=kind,
        attributes=dict(attributes or {}),
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            yield span
        except BaseException as exc:
            span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            raise


def extract_context(headers: Mapping[str, str]) -> Any:
    """Extract W3C trace context from inbound HTTP headers."""
    return TraceContextTextMapPropagator().extract(dict(headers))


def _record_route(span: Span, scope: Scope) -> None:
    template = route_template(scope)
    if template:
        span.set_attribute("http.route", template)


def _record_response(span: Span, scope: Scope, status: int) -> None:
    span.set_attribute("http.response.status_code", status)
    _record_route(span, scope)
    if status >= 500:
        span.set_status(Status(StatusCode.ERROR))


def _record_failure(
    span: Span,
    scope: Scope,
    *,
    response_started: bool,
    exc: BaseException,
) -> None:
    """Record an escaping failure without copying its text.

    ``ServerErrorMiddleware`` sits outside this middleware, so an escaping
    exception produces no ``http.response.start`` here. Record what the client
    will receive rather than leaving the span without a status code while the
    metric says 500.
    """
    if not response_started:
        span.set_attribute("http.response.status_code", 500)
        _record_route(span, scope)
    span.set_status(Status(StatusCode.ERROR, type(exc).__name__))


class TracingMiddleware:
    """Server span for incoming HTTP requests continuing W3C trace context."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    @staticmethod
    def _headers(scope: Scope) -> dict[str, str]:
        return {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in (scope.get("headers") or [])
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not instrument_scope(scope):
            await self._app(scope, receive, send)
            return

        server_span = get_tracer().start_span(
            "memory.http",
            context=extract_context(self._headers(scope)),
            kind=SpanKind.SERVER,
            attributes={"http.request.method": http_method(scope)},
        )

        response_started = False

        async def intercept_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                _record_response(server_span, scope, int(message["status"]))
            await send(message)

        with trace.use_span(
            server_span,
            end_on_exit=True,
            record_exception=False,
            set_status_on_exception=False,
        ):
            try:
                await self._app(scope, receive, intercept_send)
            except BaseException as exc:
                _record_failure(server_span, scope, response_started=response_started, exc=exc)
                raise
