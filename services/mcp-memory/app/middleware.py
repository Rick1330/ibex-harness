"""ASGI bearer auth middleware for MCP Streamable HTTP (fail closed)."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.access_token import set_access_token
from app.audit import AsyncAuditEmitter, ToolCallAuditEvent
from app.auth import TokenValidator, parse_authorization_header
from app.config import Settings
from app.errors import AuthFailedError, AuthUnavailableError
from app.principal import set_principal

logger = logging.getLogger(__name__)

ValidatorProvider = Callable[[], TokenValidator | None]
AuditProvider = Callable[[], AsyncAuditEmitter | None]

_WWW_AUTHENTICATE = 'Bearer realm="ibex-mcp", resource_metadata="{metadata_url}"'
# ClickHouse org_id is non-null; unknown identity uses the nil UUID sentinel.
AUTH_AUDIT_ORG_UNKNOWN = UUID("00000000-0000-0000-0000-000000000000")


@dataclass(frozen=True, slots=True)
class _AuthError:
    status: int
    code: str
    message: str
    www_authenticate: str | None = None


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
        get_audit: AuditProvider | None = None,
        protected_prefixes: tuple[str, ...] = ("/mcp",),
    ) -> None:
        self.app = app
        self.settings = settings
        self.get_validator = get_validator
        self.get_audit = get_audit or (lambda: None)
        self.protected_prefixes = protected_prefixes
        self._metadata_url = (
            _origin_from_resource(settings.resource_url) + "/.well-known/oauth-protected-resource"
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        if not _path_is_protected(path, self.protected_prefixes):
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        validator = self.get_validator()
        if validator is None:
            await self._reject(
                scope,
                receive,
                send,
                _AuthError(
                    status=503,
                    code="auth_unavailable",
                    message="authentication service unavailable",
                ),
                started=started,
            )
            return

        request = Request(scope, receive)
        try:
            token = parse_authorization_header(request.headers.get("authorization"))
            result = await validator.validate(token)
            set_principal(result.to_principal())
            set_access_token(token)
        except AuthFailedError as exc:
            await self._reject(
                scope,
                receive,
                send,
                _AuthError(
                    status=401,
                    code=exc.code,
                    message=exc.message,
                    www_authenticate=_WWW_AUTHENTICATE.format(metadata_url=self._metadata_url),
                ),
                started=started,
            )
            return
        except AuthUnavailableError as exc:
            await self._reject(
                scope,
                receive,
                send,
                _AuthError(status=503, code=exc.code, message=exc.message),
                started=started,
            )
            return

        try:
            await self.app(scope, receive, send)
        finally:
            set_principal(None)
            set_access_token(None)

    async def _reject(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        error: _AuthError,
        *,
        started: float,
    ) -> None:
        self._emit_auth_audit(error, started=started)
        await _send_error(scope, receive, send, error)

    def _emit_auth_audit(self, error: _AuthError, *, started: float) -> None:
        audit = self.get_audit()
        if audit is None:
            return
        latency_ms = int((time.perf_counter() - started) * 1000)
        audit.emit(
            ToolCallAuditEvent(
                request_id=str(uuid.uuid4()),
                org_id=AUTH_AUDIT_ORG_UNKNOWN,
                tool_name="auth",
                latency_ms=latency_ms,
                success=False,
                error_code=error.code,
            )
        )


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
        return parts.scheme + "://" + parts.netloc
    return url


async def _send_error(
    scope: Scope,
    receive: Receive,
    send: Send,
    error: _AuthError,
) -> None:
    headers: dict[str, str] = {"content-type": "application/json"}
    if error.www_authenticate is not None:
        headers["www-authenticate"] = error.www_authenticate
    response = JSONResponse(
        status_code=error.status,
        content={"error": {"code": error.code, "message": error.message}},
        headers=headers,
    )
    await response(scope, receive, send)
