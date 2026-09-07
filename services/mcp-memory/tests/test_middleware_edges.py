"""BearerAuthMiddleware edge paths (validator/audit missing)."""

from __future__ import annotations

import pytest

from app.auth import StaticTokenValidator
from app.config import Settings
from app.middleware import BearerAuthConfig, BearerAuthMiddleware


def _settings() -> Settings:
    return Settings(
        transport="streamable_http",
        resource_url="http://testserver/mcp",
        auth_server_url="http://auth.test",
        auth_grpc_addr="127.0.0.1:1",
        redis_url="",
    )


def _mcp_scope(*, authorization: bytes) -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/mcp",
        "raw_path": b"/mcp",
        "query_string": b"",
        "headers": [(b"authorization", authorization)],
        "client": ("127.0.0.1", 123),
        "server": ("testserver", 80),
    }


@pytest.mark.asyncio
async def test_middleware_503_when_validator_missing() -> None:
    responses: list[int] = []

    async def downstream(_scope, _receive, _send):
        raise AssertionError("downstream must not run")

    mw = BearerAuthMiddleware(
        downstream,
        BearerAuthConfig(
            settings=_settings(),
            get_validator=lambda: None,
            get_audit=lambda: None,
        ),
    )

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        if message["type"] == "http.response.start":
            responses.append(message["status"])

    await mw(_mcp_scope(authorization=b"Bearer tok"), receive, send)
    assert responses == [503]


@pytest.mark.asyncio
async def test_middleware_401_without_audit_sink() -> None:
    responses: list[int] = []

    async def downstream(_scope, _receive, _send):
        raise AssertionError("downstream must not run")

    mw = BearerAuthMiddleware(
        downstream,
        BearerAuthConfig(
            settings=_settings(),
            get_validator=lambda: StaticTokenValidator({}),
            get_audit=None,
        ),
    )

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        if message["type"] == "http.response.start":
            responses.append(message["status"])

    await mw(_mcp_scope(authorization=b"Bearer bad"), receive, send)
    assert responses == [401]
