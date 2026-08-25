"""Golden-signal HTTP metrics for the embedder service."""

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
    "1 when the embedder process is serving traffic",
)
PROCESS_UP.set(1)

HTTP_REQUESTS = Counter(
    "ibex_embedder_http_requests_total",
    "Embedder HTTP requests",
    ["method", "route", "status"],
)

HTTP_DURATION = Histogram(
    "ibex_embedder_http_request_duration_seconds",
    "Embedder HTTP request duration",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

_UNMATCHED_ROUTE = "<unmatched>"


def _route_label(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return _UNMATCHED_ROUTE


def _record(method: str, route: str, status: str, elapsed: float) -> None:
    HTTP_REQUESTS.labels(method=method, route=route, status=status).inc()
    HTTP_DURATION.labels(method=method, route=route).observe(elapsed)


class HTTPMetricsMiddleware(BaseHTTPMiddleware):
    """Record request count and latency; skip high-cardinality raw paths when possible."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)
        start = time.perf_counter()
        method = request.method
        try:
            response = await call_next(request)
        except Exception:
            elapsed = time.perf_counter() - start
            _record(method, _route_label(request), "500", elapsed)
            raise
        elapsed = time.perf_counter() - start
        _record(method, _route_label(request), str(response.status_code), elapsed)
        return response
