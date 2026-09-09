"""Auth failure types shared by Python ValidateToken dialers."""

from __future__ import annotations


class AuthFailedError(Exception):
    """Token missing, malformed, or rejected by AuthService."""


class AuthUnavailableError(Exception):
    """Auth gRPC unreachable or response unusable (fail-closed)."""
