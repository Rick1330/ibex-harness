"""Golden-signal HTTP metrics for mcp-memory."""

from __future__ import annotations

import time

from prometheus_client import Counter, Gauge, Histogram
from starlette.types import ASGIApp, Message, Receive, Scope, Send

PROCESS_UP = Gauge(
    "ibex_process_up",
    "1 when the mcp-memory process is serving traffic",
)
PROCESS_UP.set(1)

HTTP_REQUESTS = Counter(
    "ibex_mcp_http_requests_total",
    "MCP memory HTTP requests",
    ["method", "route", "status"],
)

HTTP_DURATION = Histogram(
    "ibex_mcp_http_request_duration_seconds",
    "MCP memory HTTP request duration",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

_UNMATCHED_ROUTE = "<unmatched>"


def _route_label(scope: Scope) -> str:
    path = scope.get("path", "")
    if isinstance(path, str) and path.startswith("/mcp"):
        return "/mcp"
    route = scope.get("route")
    template = getattr(route, "path", None)
    if isinstance(template, str) and template:
        return template
    return _UNMATCHED_ROUTE


def _record(method: str, route: str, status: str, elapsed: float) -> None:
    HTTP_REQUESTS.labels(method=method, route=route, status=status).inc()
    HTTP_DURATION.labels(method=method, route=route).observe(elapsed)


class HTTPMetricsMiddleware:
    """ASGI middleware: duration ends when the response body completes (more_body=false)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path == "/metrics":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        method = scope.get("method", "GET")
        if not isinstance(method, str):
            method = "GET"
        status_code = 500
        recorded = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, recorded
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)
            if (
                message["type"] == "http.response.body"
                and not message.get("more_body", False)
                and not recorded
            ):
                recorded = True
                elapsed = time.perf_counter() - start
                _record(method, _route_label(scope), str(status_code), elapsed)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            if not recorded:
                recorded = True
                elapsed = time.perf_counter() - start
                _record(method, _route_label(scope), "500", elapsed)
            raise
        if not recorded:
            elapsed = time.perf_counter() - start
            _record(method, _route_label(scope), str(status_code), elapsed)
