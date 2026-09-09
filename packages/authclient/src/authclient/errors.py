"""Auth failure types shared by Python ValidateToken dialers."""

from __future__ import annotations


class AuthFailedError(Exception):
    """Token missing, malformed, or rejected by AuthService."""


class OrgSuspendedError(AuthFailedError):
    """Token is valid but the organization is suspended."""


class AuthUnavailableError(Exception):
    """Auth gRPC unreachable or response unusable (fail-closed)."""
