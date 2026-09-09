"""Memory auth façade — dialer lives in authclient.validate (#779)."""

from __future__ import annotations

from authclient.errors import AuthFailedError, AuthUnavailableError
from authclient.validate import (
    READINESS_PROBE_SENTINEL,
    GRPCTokenValidator,
    StaticTokenValidator,
    TokenValidator,
    ValidateResult,
    parse_authorization_header,
)

__all__ = [
    "READINESS_PROBE_SENTINEL",
    "AuthFailedError",
    "AuthUnavailableError",
    "GRPCTokenValidator",
    "StaticTokenValidator",
    "TokenValidator",
    "ValidateResult",
    "parse_authorization_header",
]
