"""Golden-signal HTTP metrics for mcp-memory."""

from __future__ import annotations

from mcp_runtime.http_metrics import (
    HTTPMetricsMiddleware as _HTTPMetricsMiddleware,
)
from mcp_runtime.http_metrics import (
    build_http_metrics,
)
from starlette.types import ASGIApp

METRICS = build_http_metrics(prefix="ibex_mcp", service="mcp-memory")


class HTTPMetricsMiddleware(_HTTPMetricsMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app, METRICS)
