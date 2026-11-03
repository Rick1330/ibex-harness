"""Typed fail-closed error taxonomy for the MCP operator gateway.

Every error carries a stable ``code`` and the HTTP-equivalent ``http_status``
that documents the boundary semantics. The MCP transport surfaces these as typed
``CallToolResult(isError=true)`` results; the codes are what clients switch on.
"""

from __future__ import annotations


class GatewayError(Exception):
    """Base class for typed gateway failures (never a raw traceback to callers)."""

    code: str = "internal_error"
    http_status: int = 500

    def __init__(
        self,
        message: str = "internal gateway error",
        *,
        code: str | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if http_status is not None:
            self.http_status = http_status


class ToolNotFoundError(GatewayError):
    """The requested tool is not in the gateway registry (deny by default)."""

    code = "tool_not_found"
    http_status = 404

    def __init__(self, message: str = "unknown tool") -> None:
        super().__init__(message)


class PermissionDeniedError(GatewayError):
    """The verified principal does not hold the tool's required scope."""

    code = "permission_denied"
    http_status = 403

    def __init__(self, message: str = "insufficient permissions") -> None:
        super().__init__(message)


class NotFoundError(GatewayError):
    """The requested resource does not exist in the caller's tenant.

    Cross-tenant visibility is reported as ``not_found`` (404), never
    ``permission_denied``, to avoid leaking resource existence.
    """

    code = "not_found"
    http_status = 404

    def __init__(self, message: str = "resource not found") -> None:
        super().__init__(message)


class PolicyUnavailableError(GatewayError):
    """A configured policy authority could not decide — deny, never allow."""

    code = "policy_unavailable"
    http_status = 403

    def __init__(self, message: str = "policy authority unavailable") -> None:
        super().__init__(message)


class InvalidParamsError(GatewayError):
    """Tool arguments failed schema validation."""

    code = "invalid_params"
    http_status = 400

    def __init__(self, message: str = "invalid tool arguments") -> None:
        super().__init__(message)


class RateLimitedError(GatewayError):
    """The org exceeded its operator-gateway rate budget."""

    code = "rate_limited"
    http_status = 429

    def __init__(self, message: str = "operator gateway rate limit exceeded") -> None:
        super().__init__(message)


class RateLimitUnavailableError(GatewayError):
    """The rate-limit authority is unreachable in a fail-closed profile."""

    code = "rate_limit_unavailable"
    http_status = 503

    def __init__(self, message: str = "rate limit authority unavailable") -> None:
        super().__init__(message)


class BackendUnavailableError(GatewayError):
    """A read dependency timed out or was unreachable — fail closed."""

    code = "backend_unavailable"
    http_status = 503

    def __init__(self, message: str = "read backend unavailable") -> None:
        super().__init__(message)
