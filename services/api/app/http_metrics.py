"""Minimal Prometheus HTTP request counters."""

from __future__ import annotations

import time

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

REQUESTS = Counter(
    "ibex_api_http_requests_total",
    "Management API HTTP requests",
    ["method", "path", "status"],
)
LATENCY = Histogram(
    "ibex_api_http_request_duration_seconds",
    "Management API HTTP request latency",
    ["method", "path"],
)


class HTTPMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        method = request.method
        started = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - started
        # Bound cardinality: matched route templates only; unmatched → "other".
        route = request.scope.get("route")
        template = getattr(route, "path", None)
        label_path = template if isinstance(template, str) else "other"
        REQUESTS.labels(method=method, path=label_path, status=str(response.status_code)).inc()
        LATENCY.labels(method=method, path=label_path).observe(elapsed)
        return response
