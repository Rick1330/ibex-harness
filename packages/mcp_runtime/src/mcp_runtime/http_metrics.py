"""Golden-signal HTTP metrics middleware shared by MCP services."""

from __future__ import annotations

import time
from dataclasses import dataclass

from prometheus_client import Counter, Gauge, Histogram
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_UNMATCHED_ROUTE = "<unmatched>"


@dataclass(frozen=True, slots=True)
class HttpMetricSet:
    process_up: Gauge
    requests: Counter
    duration: Histogram


def build_http_metrics(*, prefix: str, service: str) -> HttpMetricSet:
    process_up = Gauge(
        "ibex_process_up",
        f"1 when the {service} process is serving traffic",
    )
    process_up.set(1)
    return HttpMetricSet(
        process_up=process_up,
        requests=Counter(
            f"{prefix}_http_requests_total",
            f"{service} HTTP requests",
            ["method", "route", "status"],
        ),
        duration=Histogram(
            f"{prefix}_http_request_duration_seconds",
            f"{service} HTTP request duration",
            ["method", "route"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
        ),
    )


def _route_label(scope: Scope) -> str:
    path = scope.get("path", "")
    if isinstance(path, str) and path.startswith("/mcp"):
        return "/mcp"
    route = scope.get("route")
    template = getattr(route, "path", None)
    if isinstance(template, str) and template:
        return template
    return _UNMATCHED_ROUTE


def _should_instrument(scope: Scope) -> bool:
    if scope["type"] != "http":
        return False
    return scope.get("path", "") != "/metrics"


def _request_method(scope: Scope) -> str:
    method = scope.get("method", "GET")
    return method if isinstance(method, str) else "GET"


class _RequestMetrics:
    def __init__(self, scope: Scope, metrics: HttpMetricSet) -> None:
        self._scope = scope
        self._metrics = metrics
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
        route = _route_label(self._scope)
        elapsed = time.perf_counter() - self._start
        self._metrics.requests.labels(method=self._method, route=route, status=status).inc()
        self._metrics.duration.labels(method=self._method, route=route).observe(elapsed)

    def record_error(self) -> None:
        self.record_once("500")

    def record_if_needed(self) -> None:
        self.record_once(str(self._status_code))


class HTTPMetricsMiddleware:
    """ASGI middleware: duration ends when the response body completes."""

    def __init__(self, app: ASGIApp, metrics: HttpMetricSet) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not _should_instrument(scope):
            await self.app(scope, receive, send)
            return

        metrics = _RequestMetrics(scope, self.metrics)
        try:
            await self.app(scope, receive, metrics.wrap_send(send))
        except Exception:
            metrics.record_error()
            raise
        metrics.record_if_needed()
