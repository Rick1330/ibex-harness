"""CSRF double-submit cookie enforcement for cookie-authenticated mutations (pure ASGI)."""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import Settings
from app.session_stub import verify_csrf_token

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
_CSRF_EXEMPT_PREFIXES = (
    "/health",
    "/ready",
    "/metrics",
    "/v1/operator/session/login",  # establishes cookies; no prior CSRF
)


def _header_map(scope: Scope) -> dict[str, str]:
    return {
        k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])
    }


def _cookie_map(header_value: str | None) -> dict[str, str]:
    if not header_value:
        return {}
    out: dict[str, str] = {}
    for part in header_value.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        out[name.strip()] = value.strip()
    return out


class CSRFMiddleware:
    """Require matching CSRF cookie + X-CSRF-Token when access or refresh cookie is present."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self._settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        if method in _SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if any(path == p or path.startswith(p + "/") for p in _CSRF_EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return

        headers = _header_map(scope)
        cookies = _cookie_map(headers.get("cookie"))
        access = cookies.get(self._settings.dashboard_session_cookie_name)
        refresh = cookies.get(self._settings.dashboard_refresh_cookie_name)
        if not access and not refresh:
            # Bearer-PAT callers are not cookie sessions; CSRF does not apply.
            await self.app(scope, receive, send)
            return

        secret = self._settings.dashboard_csrf_secret
        if not secret:
            response = JSONResponse(
                {"error": {"code": "csrf_misconfigured", "message": "CSRF secret not configured"}},
                status_code=503,
            )
            await response(scope, receive, send)
            return

        cookie_tok = cookies.get(self._settings.dashboard_csrf_cookie_name)
        header_tok = headers.get("x-csrf-token")
        if not verify_csrf_token(secret=secret, cookie_value=cookie_tok, header_value=header_tok):
            response = JSONResponse(
                {
                    "error": {
                        "code": "csrf_failed",
                        "message": "missing or mismatched CSRF token",
                    }
                },
                status_code=403,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
