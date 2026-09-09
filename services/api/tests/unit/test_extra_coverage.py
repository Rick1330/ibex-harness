"""Additional unit coverage for db, deps, errors, reqid, tenant."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings, get_settings
from app.db import create_engine, create_session_factory, session_with_org
from app.deps import (
    get_session_factory,
    get_validator,
    org_id_from_token,
    org_session,
    require_token,
)
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
from app.main import create_app
from app.reqid import new_id, require_current, set_current
from app.routers import tenant as tenant_mod


def test_config_empty_and_nonempty_database_url() -> None:
    assert Settings(database_url="  ").database_url is None
    assert Settings(database_url="postgresql+asyncpg://x").database_url is not None
    get_settings.cache_clear()
    a = get_settings()
    b = get_settings()
    assert a is b


def test_create_engine_paths() -> None:
    with pytest.raises(RuntimeError):
        create_engine(Settings(database_url=None))
    settings = Settings(database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex")
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    assert factory.class_ is AsyncSession


def _mock_org_session(*, execute_side_effect: object | None = None):
    session = MagicMock()
    session.execute = AsyncMock(side_effect=execute_side_effect)
    if execute_side_effect is None:
        session.execute = AsyncMock()
    begin_cm = MagicMock()
    begin_cm.__aenter__ = AsyncMock(return_value=None)
    begin_cm.__aexit__ = AsyncMock(return_value=None)
    session.begin = MagicMock(return_value=begin_cm)
    session.rollback = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory, session


@pytest.mark.asyncio
async def test_session_with_org_sets_guc_via_mock() -> None:
    factory, session = _mock_org_session()
    async with session_with_org(factory, str(uuid4())) as yielded:
        assert yielded is session
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_session_with_org_rolls_back_on_error() -> None:
    factory, session = _mock_org_session(execute_side_effect=RuntimeError("db"))
    with pytest.raises(RuntimeError):
        async with session_with_org(factory, str(uuid4())):
            pass
    session.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_error_handlers() -> None:
    set_current("22222222-2222-4222-8222-222222222222")
    settings = Settings(database_url=None)
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
    request = Request(scope)

    resp = await api_error_handler(request, ApiError(code="NOT_FOUND", message="missing"))
    assert resp.status_code == 404

    resp = await request_validation_error_handler(
        request,
        RequestValidationError([{"loc": ("body", "x"), "msg": "required", "type": "missing"}]),
    )
    assert resp.status_code == 400
    assert json.loads(resp.body)["error"]["code"] == "VALIDATION_ERROR"

    resp = await http_exception_handler(
        request,
        StarletteHTTPException(status_code=401, detail={"code": "INVALID_TOKEN", "message": "bad"}),
    )
    assert resp.status_code == 401

    resp = await http_exception_handler(
        request,
        StarletteHTTPException(status_code=401, detail="unauthorized"),
    )
    assert resp.status_code == 401
    assert json.loads(resp.body)["error"]["code"] == "INVALID_TOKEN"

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
    assert resp.status_code == 500
    assert json.loads(resp.body)["error"]["code"] == "INTERNAL_ERROR"

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


@pytest.mark.asyncio
async def test_tenant_ping_found_and_missing() -> None:
    org = uuid4()
    token = ValidateResult(org_id=org, permissions=0)
    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=org))
    )
    result = await tenant_mod.tenant_ping(token, session)
    assert result["org_id"] == str(org)

    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    with pytest.raises(ApiError) as exc:
        await tenant_mod.tenant_ping(token, session)
    assert exc.value.code == "NOT_FOUND"


def test_metrics_and_openapi() -> None:
    settings = Settings(database_url=None)
    validator = StaticTokenValidator({})
    with TestClient(create_app(settings=settings, validator=validator)) as client:
        assert client.get("/metrics").status_code == 200
        assert "paths" in client.get("/openapi.json").json()


@pytest.mark.asyncio
async def test_deps_require_token_and_org_session() -> None:
    org = uuid4()
    token = ValidateResult(org_id=org, permissions=0)
    assert org_id_from_token(token) == org

    request = MagicMock()
    request.app.state.api.validator = StaticTokenValidator({"t": token})
    request.app.state.api.session_factory = MagicMock()
    assert get_validator(request) is not None

    request.app.state.api.validator = None
    with pytest.raises(ApiError):
        get_validator(request)

    request.app.state.api.session_factory = None
    with pytest.raises(ApiError):
        get_session_factory(request)

    validator = StaticTokenValidator({"t": token})
    result = await require_token(authorization="Bearer t", validator=validator)
    assert result.org_id == org

    down = StaticTokenValidator({}, available=False)
    with pytest.raises(ApiError) as exc:
        await require_token(authorization="Bearer t", validator=down)
    assert exc.value.code == "AUTH_UNAVAILABLE"

    session = MagicMock()
    factory = MagicMock()
    with patch("app.deps.session_with_org") as sw:
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=None)
        sw.return_value = ctx
        agen = org_session(token, factory)
        yielded = await agen.__anext__()
        assert yielded is session
        await agen.aclose()


def test_reqid_fallback_and_require() -> None:
    set_current("")  # empty is still a value; clear via ContextVar reset path
    from app import reqid as reqid_mod

    token = reqid_mod._request_id_var.set(None)
    try:
        value = require_current()
        UUID(value)
    finally:
        reqid_mod._request_id_var.reset(token)

    with patch("app.reqid.uuid7", side_effect=OSError("clock")):
        UUID(new_id())
