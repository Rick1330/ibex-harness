"""Typed error mapping for tool results."""

from __future__ import annotations

from mcp_gateway import (
    BackendUnavailableError,
    InvalidParamsError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
)

from app.errors import AuthFailedError, AuthUnavailableError, ToolCallError, to_tool_call_error


def test_tool_call_error_str_includes_code() -> None:
    err = ToolCallError("permission_denied", "insufficient permissions", http_status=403)
    assert str(err) == "permission_denied: insufficient permissions"
    assert err.code == "permission_denied"
    assert err.http_status == 403


def test_to_tool_call_error_preserves_code_and_status() -> None:
    cases = [
        (PermissionDeniedError(), "permission_denied", 403),
        (NotFoundError(), "not_found", 404),
        (InvalidParamsError(), "invalid_params", 400),
        (RateLimitedError(), "rate_limited", 429),
        (BackendUnavailableError(), "backend_unavailable", 503),
    ]
    for gateway_error, code, status in cases:
        mapped = to_tool_call_error(gateway_error)
        assert isinstance(mapped, ToolCallError)
        assert mapped.code == code
        assert mapped.http_status == status


def test_auth_errors_are_typed() -> None:
    assert AuthFailedError().http_status == 401
    assert AuthUnavailableError().http_status == 503
