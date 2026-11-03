"""Typed errors for the MCP resource server."""

from __future__ import annotations


class MCPServiceError(Exception):
    """Tool failure with a stable code.

    The MCP wire format carries only ``isError`` and a text block, so the code has
    to appear in the text: a client that sees "memory service HTTP 404" cannot tell
    ``not_found`` from ``backend_rejected`` without parsing prose. ``message`` stays
    the human sentence; ``str()`` is the code-prefixed form the server emits.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class AuthFailedError(MCPServiceError):
    def __init__(self, message: str = "invalid or missing bearer token") -> None:
        super().__init__("unauthorized", message)


class AuthUnavailableError(MCPServiceError):
    def __init__(self, message: str = "authentication service unavailable") -> None:
        super().__init__("auth_unavailable", message)


class PermissionDeniedError(MCPServiceError):
    def __init__(self, message: str = "insufficient permissions") -> None:
        super().__init__("permission_denied", message)


class SchemaError(MCPServiceError):
    def __init__(self, message: str = "invalid tool arguments") -> None:
        super().__init__("invalid_params", message)


class BackendUnavailableError(MCPServiceError):
    """Memory (or other) dependency timeout / 5xx / transport — fail closed."""

    def __init__(self, message: str = "memory service unavailable") -> None:
        super().__init__("backend_unavailable", message)


class BackendRejectedError(MCPServiceError):
    """Memory returned a non-success client/server error that is not auth-shaped."""

    def __init__(self, message: str, *, code: str = "backend_error") -> None:
        super().__init__(code, message)


class RateLimitedError(MCPServiceError):
    """Org MCP RPM exceeded — surfaces as CallToolResult(isError=true)."""

    def __init__(self, message: str = "MCP rate limit exceeded") -> None:
        super().__init__("rate_limited", message)


class RateLimitUnavailableError(MCPServiceError):
    """The protected-profile rate-limit authority cannot be reached."""

    def __init__(self, message: str = "MCP rate limit service unavailable") -> None:
        super().__init__("rate_limit_unavailable", message)
