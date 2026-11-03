"""Typed errors for the MCP operator gateway.

``ToolCallError`` is what the FastMCP tool handler raises: FastMCP converts it to
``CallToolResult(isError=true)`` with the code embedded in the message. Gateway
errors keep their HTTP-equivalent status for the contract/tests.
"""

from __future__ import annotations

from mcp_gateway import GatewayError


class OperatorServiceError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int = 500) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class AuthFailedError(OperatorServiceError):
    def __init__(self, message: str = "invalid or missing bearer token") -> None:
        super().__init__("unauthorized", message, http_status=401)


class AuthUnavailableError(OperatorServiceError):
    def __init__(self, message: str = "authentication service unavailable") -> None:
        super().__init__("auth_unavailable", message, http_status=503)


class ToolCallError(OperatorServiceError):
    """Fail-closed tool result surfaced to the MCP client as an error."""

    def __init__(self, code: str, message: str, *, http_status: int = 500) -> None:
        super().__init__(code, message, http_status=http_status)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def to_tool_call_error(exc: GatewayError) -> ToolCallError:
    return ToolCallError(exc.code, exc.message, http_status=exc.http_status)
