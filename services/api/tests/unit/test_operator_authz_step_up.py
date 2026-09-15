"""Unit tests for step-up header probe and operator authz deny-by-default."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from apierror_py import INSUFFICIENT_PERMISSIONS, SERVICE_DEGRADED
from starlette.applications import Starlette
from starlette.requests import Request

from app.authz import assert_operator_permission
from app.config import Settings
from app.errors import ApiError
from app.session_stub import (
    SESSION_KIND_STEP_UP,
    TokenIssueOpts,
    issue_token_opts,
)
from app.step_up import require_step_up_header
from authclient.permissions import OPERATOR_RAW_READ, SECRET_USE


def _settings(**overrides: object) -> Settings:
    base = {
        "operator_feature_enabled": True,
        "operator_allow_raw_read": True,
        "operator_allow_secret_use": True,
        "jwt_hmac_secret": "h" * 32,
        "jwt_issuer": "ibex-harness",
        "jwt_audience": "ibex-dashboard",
    }
    base.update(overrides)
    return Settings.model_construct(**base)


def _request_with_settings(settings: Settings, *, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    app = Starlette()
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
        "headers": headers or [],
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
        "app": app,
    }
    return Request(scope)


def test_assert_operator_permission_feature_kill_switch() -> None:
    with pytest.raises(ApiError) as exc:
        assert_operator_permission(
            _settings(operator_feature_enabled=False),
            OPERATOR_RAW_READ,
            OPERATOR_RAW_READ,
            step_up_ok=True,
        )
    assert exc.value.code == SERVICE_DEGRADED


def test_assert_operator_permission_action_kill_switch() -> None:
    with pytest.raises(ApiError) as exc:
        assert_operator_permission(
            _settings(operator_allow_raw_read=False),
            OPERATOR_RAW_READ,
            OPERATOR_RAW_READ,
            step_up_ok=True,
        )
    assert exc.value.code == INSUFFICIENT_PERMISSIONS


def test_assert_operator_permission_requires_step_up() -> None:
    with pytest.raises(ApiError) as exc:
        assert_operator_permission(
            _settings(),
            OPERATOR_RAW_READ,
            OPERATOR_RAW_READ,
            step_up_ok=False,
        )
    assert "Step-up" in exc.value.message


def test_assert_operator_permission_ok_with_step_up() -> None:
    assert_operator_permission(
        _settings(),
        OPERATOR_RAW_READ,
        OPERATOR_RAW_READ,
        step_up_ok=True,
    )


@pytest.mark.asyncio
async def test_step_up_header_missing_sets_false() -> None:
    req = _request_with_settings(_settings())
    await require_step_up_header(req)
    assert req.state.ibex_step_up_ok is False


@pytest.mark.asyncio
async def test_step_up_header_valid_sets_true() -> None:
    settings = _settings()
    token = issue_token_opts(
        TokenIssueOpts(
            secret=settings.jwt_hmac_secret or "h" * 32,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            org_id=uuid4(),
            permissions=SECRET_USE,
            subject="user-1",
            session_kind=SESSION_KIND_STEP_UP,
            ttl_seconds=300,
        )
    )
    req = _request_with_settings(settings, headers=[(b"x-ibex-step-up", token.encode())])
    await require_step_up_header(req)
    assert req.state.ibex_step_up_ok is True


@pytest.mark.asyncio
async def test_step_up_header_expired_denies() -> None:
    settings = _settings()
    token = issue_token_opts(
        TokenIssueOpts(
            secret=settings.jwt_hmac_secret or "h" * 32,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            org_id=uuid4(),
            permissions=0,
            subject="user-1",
            session_kind=SESSION_KIND_STEP_UP,
            ttl_seconds=-10,
        )
    )
    req = _request_with_settings(settings, headers=[(b"x-ibex-step-up", token.encode())])
    with pytest.raises(ApiError) as exc:
        await require_step_up_header(req)
    assert exc.value.code == INSUFFICIENT_PERMISSIONS
