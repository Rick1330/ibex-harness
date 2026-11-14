"""JSON error envelope for exceptions the memory HTTP surface does not handle.

This module guarantees two things and one thing only:

* The **response** never carries exception text or stack detail. Either can echo
  memory content or SQL with bound parameters.
* This handler's own log record carries the exception type, the request method and
  the route path. The request body, query and headers are never logged, and
  ``exc_info`` is not passed, so that record holds no traceback.

It does **not** keep exception text out of the process log. FastAPI registers this
handler for ``Exception``, so it runs inside Starlette's ``ServerErrorMiddleware``,
which re-raises the exception after the response has been sent
(``starlette/middleware/errors.py``:186 in Starlette 1.6.0) so the ASGI server can
log it. Uvicorn then logs ``Exception in ASGI application`` with the full
traceback, whose final line is ``RuntimeError: <message>``.

That is a rule for raise sites rather than a suppression: an exception **message**
must not embed memory content, SQL with bound parameters, or any other tenant data,
because the message can reach the ASGI server's log. Log the identifier, not the
content. ``TestClient(raise_server_exceptions=False)`` never observes that path,
so a test that only asserts on this handler cannot prove the log is clean.
"""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

INTERNAL_ERROR = "INTERNAL_ERROR"
_INTERNAL_MESSAGE = "An unexpected error occurred"


def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render an unexpected exception as the stable 500 JSON envelope."""
    # AGENTS.md §8.1 requires every REST error to use the documented envelope.
    # FastAPI handles ``RequestValidationError`` explicitly (``app.http_validation``),
    # but an unhandled exception falls through to Starlette's
    # ``ServerErrorMiddleware``, which renders a plain-text ``Internal Server Error``
    # body that no client can parse.
    #
    # Only the exception type, method, and route path reach *this* record: the
    # request body, query, and headers can carry memory content and are never
    # logged, and ``exc_info`` is omitted so no traceback is attached here. The
    # ASGI server still logs the re-raised exception (see the module docstring),
    # which is why ``str(exc)`` must never carry content.
    logger.error(
        "unhandled exception type=%s method=%s path=%s",
        type(exc).__name__,
        request.method,
        request.url.path,
    )
    # The response carries no exception text or stack detail: either can echo
    # memory content or SQL.
    return JSONResponse(
        status_code=500,
        content={"error": {"code": INTERNAL_ERROR, "message": _INTERNAL_MESSAGE}},
    )
