"""Golden-signal HTTP metrics for mcp-memory."""

from __future__ import annotations

import time
from collections.abc import Callable

from prometheus_client import Counter, Gauge, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

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


def _route_label(request: Request) -> str:
    path = request.url.path
    if path.startswith("/mcp"):
        return "/mcp"
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    if isinstance(template, str) and template:
        return template
    return path


class HTTPMetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        route = _route_label(request)
        method = request.method
        status = str(response.status_code)
        HTTP_REQUESTS.labels(method=method, route=route, status=status).inc()
        HTTP_DURATION.labels(method=method, route=route).observe(elapsed)
        return response
