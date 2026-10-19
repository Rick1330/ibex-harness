"""Request-scoped gateway principal via contextvars (never stores tokens)."""

from __future__ import annotations

from contextvars import ContextVar

from mcp_gateway import GatewayPrincipal

_principal: ContextVar[GatewayPrincipal | None] = ContextVar("mcp_operator_principal", default=None)


def set_principal(principal: GatewayPrincipal | None) -> None:
    _principal.set(principal)


def get_principal() -> GatewayPrincipal | None:
    return _principal.get()


def require_principal() -> GatewayPrincipal:
    principal = _principal.get()
    if principal is None:
        raise RuntimeError("tool invoked without authenticated principal")
    return principal
