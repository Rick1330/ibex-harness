"""CORS allow-list middleware for the operator UI (credentials allowed; never *)."""

from __future__ import annotations

from collections.abc import Sequence

from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp


def build_cors_middleware(
    app: ASGIApp,
    *,
    allow_origins: Sequence[str],
) -> CORSMiddleware:
    """Wrap ``app`` with Starlette CORS limited to an explicit origin allow-list."""
    origins = [o for o in allow_origins if o and o != "*"]
    return CORSMiddleware(
        app,
        allow_origins=list(origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Request-ID",
            "X-CSRF-Token",
            "Last-Event-ID",
            "Accept",
        ],
        expose_headers=["X-Request-ID", "X-IBEX-Drain"],
        max_age=600,
    )
