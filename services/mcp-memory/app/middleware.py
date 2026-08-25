"""ASGI bearer auth middleware for MCP Streamable HTTP (fail closed)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.auth import TokenValidator, parse_authorization_header
from app.config import Settings
from app.errors import AuthFailedError, AuthUnavailableError
from app.principal import set_principal

logger = logging.getLogger(__name__)

ValidatorProvider = Callable[[], TokenValidator | None]

_WWW_AUTHENTICATE = 'Bearer realm="ibex-mcp", resource_metadata="{metadata_url}"'


class BearerAuthMiddleware:
    """Pure ASGI middleware — BaseHTTPMiddleware breaks Streamable HTTP streaming.

    Uses a provider so the validator can be wired during lifespan without
    reconstructing middleware on every request.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Settings,
        get_validator: ValidatorProvider,
        protected_prefixes: tuple[str, ...] = ("/mcp",),
    ) -> None:
        self.app = app
        self.settings = settings
        self.get_validator = get_validator
        self.protected_prefixes = protected_prefixes
        self._metadata_url = (
            f"{_origin_from_resource(settings.resource_url)}"
            f"/.well-known/oauth-protected-resource"
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        if not _path_is_protected(path, self.protected_prefixes):
            await self.app(scope, receive, send)
            return

        validator = self.get_validator()
        if validator is None:
            await _send_error(
                scope,
                receive,
                send,
                status=503,
                code="auth_unavailable",
                message="authentication service unavailable",
            )
            return

        request = Request(scope, receive)
        try:
            token = parse_authorization_header(request.headers.get("authorization"))
            result = await validator.validate(token)
            set_principal(result.to_principal())
        except AuthFailedError as exc:
            await _send_error(
                scope,
                receive,
                send,
                status=401,
                code=exc.code,
                message=exc.message,
                www_authenticate=_WWW_AUTHENTICATE.format(metadata_url=self._metadata_url),
            )
            return
        except AuthUnavailableError as exc:
            await _send_error(
                scope,
                receive,
                send,
                status=503,
                code=exc.code,
                message=exc.message,
            )
            return

        try:
            await self.app(scope, receive, send)
        finally:
            set_principal(None)


def _path_is_protected(path: str, prefixes: tuple[str, ...]) -> bool:
    for prefix in prefixes:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def _origin_from_resource(resource_url: str) -> str:
    """Derive the public origin used for resource-metadata discovery links."""
    url = resource_url.rstrip("/")
    if url.endswith("/mcp"):
        return url[: -len("/mcp")] or url
    parts = urlsplit(url)
    if parts.scheme and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}"
    return url


async def _send_error(
    scope: Scope,
    receive: Receive,
    send: Send,
    *,
    status: int,
    code: str,
    message: str,
    www_authenticate: str | None = None,
) -> None:
    headers: dict[str, str] = {"content-type": "application/json"}
    if www_authenticate is not None:
        headers["www-authenticate"] = www_authenticate
    response = JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
        headers=headers,
    )
    await response(scope, receive, send)
