"""Request-scoped principal via contextvars (never store tokens)."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID

_principal: ContextVar[Principal | None] = ContextVar("mcp_principal", default=None)


@dataclass(frozen=True, slots=True)
class Principal:
    org_id: UUID
    permissions: int
    agent_id: UUID | None = None
    user_id: str | None = None
    token_id: str | None = None


def set_principal(principal: Principal | None) -> None:
    _principal.set(principal)


def get_principal() -> Principal | None:
    return _principal.get()


def require_principal() -> Principal:
    principal = _principal.get()
    if principal is None:
        raise RuntimeError("tool invoked without authenticated principal")
    return principal
