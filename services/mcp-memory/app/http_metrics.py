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


def _should_instrument(scope: Scope) -> bool:
    if scope["type"] != "http":
        return False
    return scope.get("path", "") != "/metrics"


def _request_method(scope: Scope) -> str:
    method = scope.get("method", "GET")
    if isinstance(method, str):
        return method
    return "GET"


class _RequestMetrics:
    """Records once when the response body completes, or on error/fallback."""

    def __init__(self, scope: Scope) -> None:
        self._scope = scope
        self._method = _request_method(scope)
        self._start = time.perf_counter()
        self._status_code = 500
        self._recorded = False

    def wrap_send(self, send: Send) -> Send:
        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                self._status_code = int(message["status"])
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                self.record_once(str(self._status_code))

        return send_wrapper

    def record_once(self, status: str) -> None:
        if self._recorded:
            return
        self._recorded = True
        elapsed = time.perf_counter() - self._start
        _record(self._method, _route_label(self._scope), status, elapsed)

    def record_error(self) -> None:
        self.record_once("500")

    def record_if_needed(self) -> None:
        self.record_once(str(self._status_code))


class HTTPMetricsMiddleware:
    """ASGI middleware: duration ends when the response body completes (more_body=false)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not _should_instrument(scope):
            await self.app(scope, receive, send)
            return

        metrics = _RequestMetrics(scope)
        try:
            await self.app(scope, receive, metrics.wrap_send(send))
        except Exception:
            metrics.record_error()
            raise
        metrics.record_if_needed()
