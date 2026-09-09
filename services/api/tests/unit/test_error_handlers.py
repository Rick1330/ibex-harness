"""Unit tests for FastAPI exception handlers → IBEX envelope."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app.config import Settings
from app.errors import (
    ApiError,
    ResponseOpts,
    api_error_handler,
    auth_failed_response,
    auth_unavailable_response,
    envelope_response,
    http_exception_handler,
    request_validation_error_handler,
    unhandled_error_handler,
)
from app.reqid import set_current


def _request(settings: Settings) -> Request:
    app = FastAPI()
    app.state.settings = settings
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1),
        "server": ("127.0.0.1", 80),
        "app": app,
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_api_and_validation_handlers() -> None:
    set_current("22222222-2222-4222-8222-222222222222")
    request = _request(Settings(database_url=None))

    resp = await api_error_handler(request, ApiError(code="NOT_FOUND", message="missing"))
    assert resp.status_code == 404

    resp = await request_validation_error_handler(
        request,
        RequestValidationError([{"loc": ("body", "x"), "msg": "required", "type": "missing"}]),
    )
    assert resp.status_code == 400
    assert json.loads(resp.body)["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_http_exception_dict_and_status_mapping() -> None:
    set_current("22222222-2222-4222-8222-222222222222")
    request = _request(Settings(database_url=None))

    resp = await http_exception_handler(
        request,
        StarletteHTTPException(status_code=401, detail={"code": "INVALID_TOKEN", "message": "bad"}),
    )
    assert resp.status_code == 401

    resp = await http_exception_handler(
        request,
        StarletteHTTPException(status_code=401, detail="unauthorized"),
    )
    assert json.loads(resp.body)["error"]["code"] == "INVALID_TOKEN"

    resp = await http_exception_handler(
        request,
        StarletteHTTPException(status_code=403, detail="forbidden"),
    )
    assert resp.status_code == 403
    assert json.loads(resp.body)["error"]["code"] == "INSUFFICIENT_PERMISSIONS"

    resp = await http_exception_handler(
        request,
        StarletteHTTPException(status_code=404, detail="gone"),
    )
    assert resp.status_code == 404

    resp = await http_exception_handler(
        request,
        StarletteHTTPException(status_code=503, detail="down"),
    )
    assert resp.status_code == 503

    resp = await http_exception_handler(
        request,
        StarletteHTTPException(status_code=400, detail="bad"),
    )
    assert resp.status_code == 400

    resp = await http_exception_handler(
        request,
        StarletteHTTPException(status_code=500, detail="boom"),
    )
    assert json.loads(resp.body)["error"]["code"] == "INTERNAL_ERROR"


@pytest.mark.asyncio
async def test_http_exception_incomplete_detail_dict() -> None:
    set_current("22222222-2222-4222-8222-222222222222")
    request = _request(Settings(database_url=None))

    resp = await http_exception_handler(
        request,
        StarletteHTTPException(status_code=400, detail={"code": "X"}),
    )
    assert resp.status_code == 400

    resp = await http_exception_handler(
        request,
        StarletteHTTPException(status_code=400, detail={"message": "only"}),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_unhandled_and_auth_helpers() -> None:
    set_current("22222222-2222-4222-8222-222222222222")
    settings = Settings(database_url=None)
    request = _request(settings)

    resp = await unhandled_error_handler(request, RuntimeError("x"))
    assert resp.status_code == 500

    assert auth_failed_response("missing authorization header", settings).status_code == 401
    assert auth_failed_response("invalid token", settings).status_code == 401
    assert auth_unavailable_response(settings).status_code == 503
    assert envelope_response(code="INTERNAL_ERROR", message="x").status_code == 500
    assert (
        envelope_response(
            code="INTERNAL_ERROR",
            message="x",
            opts=ResponseOpts(settings=None),
        ).status_code
        == 500
    )
