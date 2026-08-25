"""Typed errors for the MCP resource server."""

from __future__ import annotations


class MCPServiceError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


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
