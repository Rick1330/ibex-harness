"""Request-scoped access token for memory HTTP forwarding (never log)."""

from __future__ import annotations

from contextvars import ContextVar

from app.errors import AuthFailedError

_access_token: ContextVar[str | None] = ContextVar("mcp_access_token", default=None)


def set_access_token(token: str | None) -> None:
    _access_token.set(token)


def get_access_token() -> str | None:
    return _access_token.get()


def require_access_token() -> str:
    """Bearer material for outbound memory calls — must not be logged."""
    token = _access_token.get()
    if token is None or not token.strip():
        raise AuthFailedError("missing bearer token for memory service call")
    return token
