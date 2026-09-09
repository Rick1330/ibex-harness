"""Auth-specific errors (fail closed on unavailable)."""

from __future__ import annotations


class AuthFailedError(Exception):
    """Invalid or missing bearer token."""


class AuthUnavailableError(Exception):
    """Auth gRPC unreachable."""
