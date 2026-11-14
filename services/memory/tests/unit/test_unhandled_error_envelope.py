"""Unhandled exceptions render the JSON envelope; the ASGI server still logs them.

What these tests prove: the client gets the stable envelope, and the handler's own
log record carries no exception text. What they do **not** prove: that the process
log is free of the message. Starlette's ``ServerErrorMiddleware`` re-raises after
the handler runs, so the ASGI server logs the traceback. The last test pins that
re-raise so the narrower guarantee cannot be re-read as a broader one.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.client import StaticTokenValidator
from app.config import Settings
from app.main import create_app

_LEAK = "memory-content-must-not-leak"


def _app_with_failing_route() -> FastAPI:
    app = create_app(
        settings=Settings(database_url=""),
        validator=StaticTokenValidator({}, available=True),
    )

    @app.get("/boom")
    async def boom() -> None:
        msg = f"write failed for {_LEAK}"
        raise RuntimeError(msg)

    return app


def test_unhandled_exception_returns_envelope_and_a_content_free_handler_record(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = _app_with_failing_route()
    # Starlette's ServerErrorMiddleware re-raises after writing the response; the
    # client is what must see the envelope, so do not let TestClient re-raise.
    # This client never observes the ASGI-level traceback, which is why the
    # assertions below are scoped to the response and to this handler's record.
    with (
        caplog.at_level(logging.ERROR, logger="app.errors"),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        resp = client.get("/boom")

    assert resp.status_code == 500
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {
        "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"},
    }
    # The response never echoes the exception text or its type.
    assert _LEAK not in resp.text
    assert "RuntimeError" not in resp.text

    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "unhandled exception type=RuntimeError method=GET path=/boom" in message
        for message in messages
    )

    # The handler's record is the leak path it controls: it names the type, method
    # and path, and carries no traceback. This says nothing about the ASGI server's
    # record of the re-raised exception — see the next test.
    assert _LEAK not in caplog.text
    for record in caplog.records:
        assert _LEAK not in record.getMessage()
        assert record.exc_info is None
        assert record.exc_text is None


def test_unhandled_exception_is_reraised_to_the_asgi_server() -> None:
    """Pin the re-raise: the ASGI server, not this handler, logs the traceback."""
    app = _app_with_failing_route()
    with (
        TestClient(app, raise_server_exceptions=True) as client,
        pytest.raises(RuntimeError, match=_LEAK),
    ):
        client.get("/boom")
