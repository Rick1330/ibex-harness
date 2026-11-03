"""Pure ASGI bearer-auth middleware shared by MCP services (fail closed)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

# ClickHouse org_id is non-null; unknown identity uses the nil UUID sentinel.
AUTH_AUDIT_ORG_UNKNOWN = UUID("00000000-0000-0000-0000-000000000000")


class Validator[PrincipalT](Protocol):
    async def validate(self, access_token: str) -> PrincipalT: ...


@dataclass(frozen=True, slots=True)
class BearerAuthConfig[PrincipalT]:
    realm: str
    resource_url: str
    get_validator: Callable[[], Validator[PrincipalT] | None]
    parse_token: Callable[[str | None], str]
    bind_principal: Callable[[str, PrincipalT], None]
    clear_principal: Callable[[], None]
    auth_failed_error: type[Exception]
    auth_unavailable_error: type[Exception]
    emit_deny: Callable[[str, int], None] | None = None
    protected_prefixes: tuple[str, ...] = ("/mcp",)


@dataclass(frozen=True, slots=True)
class _AuthError:
    status: int
    code: str
    message: str
    www_authenticate: str | None = None


@dataclass(frozen=True, slots=True)
class _AsgiCall:
    scope: Scope
    receive: Receive
    send: Send


@dataclass(frozen=True, slots=True)
class _RejectRequest:
    call: _AsgiCall
    error: _AuthError
    started: float


class BearerAuthMiddleware[PrincipalT]:
    """Validates the bearer token and binds a token-derived principal.

    Pure ASGI — ``BaseHTTPMiddleware`` breaks Streamable HTTP streaming.
    """

    def __init__(self, app: ASGIApp, config: BearerAuthConfig[PrincipalT]) -> None:
        self.app = app
        self.config = config
        self._metadata_url = (
            origin_from_resource(config.resource_url) + "/.well-known/oauth-protected-resource"
        )
        self._www_authenticate = (
            f'Bearer realm="{config.realm}", resource_metadata="{{metadata_url}}"'
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        if not path_is_protected(path, self.config.protected_prefixes):
            await self.app(scope, receive, send)
            return

        call = _AsgiCall(scope=scope, receive=receive, send=send)
        started = time.perf_counter()
        validator = self.config.get_validator()
        if validator is None:
            await self._reject(
                _RejectRequest(
                    call=call,
                    error=_AuthError(
                        status=503,
                        code="auth_unavailable",
                        message="authentication service unavailable",
                    ),
                    started=started,
                )
            )
            return

        request = Request(scope, receive)
        try:
            token = self.config.parse_token(request.headers.get("authorization"))
            principal = await validator.validate(token)
            self.config.bind_principal(token, principal)
        except self.config.auth_failed_error as exc:
            error = _as_auth_error(exc, status=401)
            await self._reject(
                _RejectRequest(
                    call=call,
                    error=_AuthError(
                        status=error.status,
                        code=error.code,
                        message=error.message,
                        www_authenticate=self._www_authenticate.format(
                            metadata_url=self._metadata_url
                        ),
                    ),
                    started=started,
                )
            )
            return
        except self.config.auth_unavailable_error as exc:
            await self._reject(
                _RejectRequest(
                    call=call,
                    error=_as_auth_error(exc, status=503),
                    started=started,
                )
            )
            return

        try:
            await self.app(scope, receive, send)
        finally:
            self.config.clear_principal()

    async def _reject(self, req: _RejectRequest) -> None:
        self._emit_deny(req.error.code, started=req.started)
        await _send_error(req.call, req.error)

    def _emit_deny(self, error_code: str, *, started: float) -> None:
        if self.config.emit_deny is None:
            return
        latency_ms = int((time.perf_counter() - started) * 1000)
        self.config.emit_deny(error_code, latency_ms)


def _as_auth_error(exc: Exception, *, status: int) -> _AuthError:
    code = str(getattr(exc, "code", "auth_failed"))
    message = str(getattr(exc, "message", str(exc)))
    return _AuthError(status=status, code=code, message=message)


def path_is_protected(path: str, prefixes: tuple[str, ...]) -> bool:
    for prefix in prefixes:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def origin_from_resource(resource_url: str) -> str:
    url = resource_url.rstrip("/")
    if url.endswith("/mcp"):
        return url[: -len("/mcp")] or url
    parts = urlsplit(url)
    if parts.scheme and parts.netloc:
        return parts.scheme + "://" + parts.netloc
    return url


async def _send_error(call: _AsgiCall, error: _AuthError) -> None:
    headers: dict[str, str] = {"content-type": "application/json"}
    if error.www_authenticate is not None:
        headers["www-authenticate"] = error.www_authenticate
    response = JSONResponse(
        status_code=error.status,
        content={"error": {"code": error.code, "message": error.message}},
        headers=headers,
    )
    await response(call.scope, call.receive, call.send)
