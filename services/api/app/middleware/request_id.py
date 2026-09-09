"""ASGI middleware that assigns / echoes X-Request-ID."""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.reqid import HEADER, resolve_inbound, set_current


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        request_id = resolve_inbound(headers.get(HEADER.lower()))
        set_current(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers", []))
                raw_headers.append((HEADER.lower().encode("latin-1"), request_id.encode("latin-1")))
                message = {**message, "headers": raw_headers}
            await send(message)

        await self.app(scope, receive, send_with_request_id)
