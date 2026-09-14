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


def _path_is_csrf_exempt(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in _CSRF_EXEMPT_PREFIXES)


def _csrf_json(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status_code)


class CSRFMiddleware:
    """Require matching CSRF cookie + X-CSRF-Token when access or refresh cookie is present."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self._settings = settings

    def _should_skip(self, scope: Scope) -> bool:
        if scope["type"] != "http":
            return True
        method = scope.get("method", "GET").upper()
        if method in _SAFE_METHODS:
            return True
        return _path_is_csrf_exempt(scope.get("path", ""))

    def _session_cookies_present(self, cookies: dict[str, str]) -> bool:
        access = cookies.get(self._settings.dashboard_session_cookie_name)
        refresh = cookies.get(self._settings.dashboard_refresh_cookie_name)
        return bool(access or refresh)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._should_skip(scope):
            await self.app(scope, receive, send)
            return

        headers = _header_map(scope)
        cookies = _cookie_map(headers.get("cookie"))
        if not self._session_cookies_present(cookies):
            # Bearer-PAT callers are not cookie sessions; CSRF does not apply.
            await self.app(scope, receive, send)
            return

        secret = self._settings.dashboard_csrf_secret
        if not secret:
            await _csrf_json(
                "csrf_misconfigured", "CSRF secret not configured", 503
            )(scope, receive, send)
            return

        cookie_tok = cookies.get(self._settings.dashboard_csrf_cookie_name)
        header_tok = headers.get("x-csrf-token")
        if not verify_csrf_token(secret=secret, cookie_value=cookie_tok, header_value=header_tok):
            await _csrf_json(
                "csrf_failed", "missing or mismatched CSRF token", 403
            )(scope, receive, send)
            return

        await self.app(scope, receive, send)
