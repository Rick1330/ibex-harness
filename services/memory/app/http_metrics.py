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


def _route_label(scope: Scope) -> str:
    route = scope.get("route")
    template = getattr(route, "path", None)
    if isinstance(template, str) and template:
        return template
    return _UNMATCHED_ROUTE


def _instrument(scope: Scope) -> bool:
    return scope.get("type") == "http" and scope.get("path") != "/metrics"


class HTTPMetricsMiddleware:
    """ASGI middleware: count + latency with status labels; skip /metrics."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not _instrument(scope):
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        if not isinstance(method, str):
            method = "GET"
        start = time.perf_counter()
        status_code = 500
        recorded = False

        def observe(status: str) -> None:
            nonlocal recorded
            if recorded:
                return
            recorded = True
            route = _route_label(scope)
            HTTP_REQUESTS.labels(method=method, route=route, status=status).inc()
            HTTP_DURATION.labels(method=method, route=route).observe(
                time.perf_counter() - start
            )

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                observe(str(status_code))

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            observe("500")
            raise
        observe(str(status_code))
