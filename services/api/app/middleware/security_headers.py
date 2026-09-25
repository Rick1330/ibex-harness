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
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {key.lower() for key, _ in headers}
                if is_api and b"cache-control" not in existing:
                    headers.append((b"cache-control", b"no-store"))
                if is_sse:
                    if b"cache-control" not in existing:
                        headers.append((b"cache-control", b"no-cache, no-store"))
                    if b"x-accel-buffering" not in existing:
                        headers.append((b"x-accel-buffering", b"no"))
                if b"x-content-type-options" not in existing:
                    headers.append((b"x-content-type-options", b"nosniff"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
