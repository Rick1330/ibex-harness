"""Auth failure types shared by Python ValidateToken dialers."""

from __future__ import annotations


class AuthFailedError(Exception):
    """Token missing, malformed, or rejected by AuthService."""


class OrgSuspendedError(AuthFailedError):
    """Token is valid but the organization is suspended."""


class AuthUnavailableError(Exception):
    """Auth gRPC unreachable or response unusable (fail-closed)."""


class TokenNotFoundError(Exception):
    """Strict revoke/list: token missing or cross-tenant (anti-enumeration)."""


class InsufficientPermissionsError(Exception):
    """Caller lacks TokenCreate (or equivalent) for a management RPC."""
