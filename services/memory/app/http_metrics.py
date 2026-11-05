"""Golden-signal HTTP metrics for the memory service (pure ASGI)."""

from __future__ import annotations

import time

from prometheus_client import Counter, Gauge, Histogram
from starlette.types import ASGIApp, Message, Receive, Scope, Send

PROCESS_UP = Gauge(
    "ibex_process_up",
    "1 when the memory process is serving traffic",
)
PROCESS_UP.set(1)

HTTP_REQUESTS = Counter(
    "ibex_memory_http_requests_total",
    "Memory HTTP requests",
    ["method", "route", "status"],
)

HTTP_DURATION = Histogram(
    "ibex_memory_http_request_duration_seconds",
    "Memory HTTP request duration",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

_UNMATCHED_ROUTE = "<unmatched>"

# HTTP methods are caller-controlled tokens. Only the registered set may become a
# span attribute or a Prometheus label; anything else collapses to ``_OTHER`` so a
# crafted method cannot inject a UUID and explode label cardinality.
_KNOWN_METHODS = frozenset(
    {"GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", "TRACE", "PATCH"}
)


def http_method(scope: Scope) -> str:
    """Bounded method label for spans and metrics."""
    method = scope.get("method", "GET")
    if isinstance(method, str) and method in _KNOWN_METHODS:
        return method
    return "_OTHER"


def route_template(scope: Scope) -> str | None:
    """Route template for an already-routed request, or None when unknown.

    FastAPI's ``APIRoute.matches`` stores the matched route in ``scope["route"]``.
    The built-in plain-Starlette routes (``/docs``, ``/openapi.json``) store
    nothing, and a mounted sub-app stores only its inner template without the
    mount prefix. Callers treat ``None`` as "no template" and omit the attribute
    rather than inventing a raw path.

    Shared with the tracing middleware so the metric label and the ``http.route``
    span attribute resolve a request the same way.
    """
    route = scope.get("route")
    template = getattr(route, "path", None)
    if isinstance(template, str) and template:
        return template
    return None


def route_label(scope: Scope) -> str:
    """Metric label: the route template, or a bounded placeholder when unmatched."""
    return route_template(scope) or _UNMATCHED_ROUTE


def instrument_scope(scope: Scope) -> bool:
    """True for instrumented HTTP traffic; ``/metrics`` stays out of metrics and spans."""
    return scope.get("type") == "http" and scope.get("path") != "/metrics"


def _request_method(scope: Scope) -> str:
    return http_method(scope)


class _Recorder:
    """Records request metrics once (on body complete, error, or fallback)."""

    def __init__(self, scope: Scope) -> None:
        self._scope = scope
        self._method = _request_method(scope)
        self._start = time.perf_counter()
        self._status_code = 500
        self._done = False

    def wrap_send(self, send: Send) -> Send:
        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                self._status_code = int(message["status"])
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                self.finish(str(self._status_code))

        return send_wrapper

    def finish(self, status: str) -> None:
        if self._done:
            return
        self._done = True
        route = route_label(self._scope)
        HTTP_REQUESTS.labels(method=self._method, route=route, status=status).inc()
        HTTP_DURATION.labels(method=self._method, route=route).observe(
            time.perf_counter() - self._start
        )

    def finish_error(self) -> None:
        self.finish("500")

    def finish_if_needed(self) -> None:
        self.finish(str(self._status_code))


class HTTPMetricsMiddleware:
    """ASGI middleware: count + latency with status labels; skip /metrics."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not instrument_scope(scope):
            await self.app(scope, receive, send)
            return

        recorder = _Recorder(scope)
        try:
            await self.app(scope, receive, recorder.wrap_send(send))
        except Exception:
            recorder.finish_error()
            raise
        recorder.finish_if_needed()
