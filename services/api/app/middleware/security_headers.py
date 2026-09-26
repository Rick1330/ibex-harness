"""Security response headers for authenticated API and event-stream responses."""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        is_api = path.startswith("/v1/")
        is_sse = path.endswith("/events/stream")

        async def send_with_headers(message: Message) -> None:
            await send(_add_security_headers(message, is_api=is_api, is_sse=is_sse))

        await self.app(scope, receive, send_with_headers)


def _add_security_headers(message: Message, *, is_api: bool, is_sse: bool) -> Message:
    if message["type"] != "http.response.start":
        return message
    headers = list(message.get("headers", []))
    existing = {key.lower() for key, _ in headers}
    _append_if_missing(headers, existing, b"x-content-type-options", b"nosniff")
    if is_sse:
        _append_if_missing(headers, existing, b"cache-control", b"no-cache, no-store")
        _append_if_missing(headers, existing, b"x-accel-buffering", b"no")
    elif is_api:
        _append_if_missing(headers, existing, b"cache-control", b"no-store")
    return {**message, "headers": headers}


def _append_if_missing(
    headers: list[tuple[bytes, bytes]], existing: set[bytes], name: bytes, value: bytes
) -> None:
    if name not in existing:
        headers.append((name, value))
        existing.add(name)
