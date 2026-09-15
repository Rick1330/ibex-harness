"""Unit tests for step-up header probe and operator authz deny-by-default."""

from __future__ import annotations

from uuid import uuid4

import pytest
from apierror_py import INSUFFICIENT_PERMISSIONS, SERVICE_DEGRADED
from authclient.permissions import OPERATOR_RAW_READ, SECRET_USE
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


@pytest.mark.parametrize(
    ("settings_kw", "want_code"),
    [
        ({"operator_feature_enabled": False}, SERVICE_DEGRADED),
        ({"operator_allow_raw_read": False}, INSUFFICIENT_PERMISSIONS),
        ({}, None),  # missing step-up handled below via step_up_ok
    ],
)
def test_assert_operator_permission_denies(settings_kw: dict, want_code: str | None) -> None:
    settings = _settings(**settings_kw)
    step_up_ok = want_code is not None
    if want_code is None:
        # requires step-up when step_up_ok is False
        with pytest.raises(ApiError) as exc:
            assert_operator_permission(
                settings, OPERATOR_RAW_READ, OPERATOR_RAW_READ, step_up_ok=False
            )
        assert "Step-up" in exc.value.message
        return
    with pytest.raises(ApiError) as exc:
        assert_operator_permission(
            settings, OPERATOR_RAW_READ, OPERATOR_RAW_READ, step_up_ok=step_up_ok
        )
    assert exc.value.code == want_code


def test_assert_operator_permission_ok_with_step_up() -> None:
    assert_operator_permission(
        _settings(),
        OPERATOR_RAW_READ,
        OPERATOR_RAW_READ,
        step_up_ok=True,
    )


def test_assert_operator_permission_bitmap_missing() -> None:
    settings = _settings()
    with pytest.raises(ApiError) as exc:
        assert_operator_permission(
            settings,
            0,
            OPERATOR_RAW_READ,
            step_up_ok=True,
        )
    assert exc.value.code == INSUFFICIENT_PERMISSIONS
    assert "Insufficient permissions" in exc.value.message


def test_require_operator_permission_dep_reads_step_up_flag() -> None:
    from app.auth.client import ValidateResult
    from app.authz import require_operator_permission

    org = uuid4()
    token = ValidateResult(org_id=org, permissions=SECRET_USE, user_id="u1")
    dep = require_operator_permission(SECRET_USE)
    req = _request_with_settings(_settings(operator_allow_secret_use=True))
    req.state.ibex_step_up_ok = False
    with pytest.raises(ApiError) as exc:
        dep(req, token)
    assert "Step-up" in exc.value.message
    req.state.ibex_step_up_ok = True
    assert dep(req, token) is token


def test_step_up_header_missing_sets_false() -> None:
    req = _request_with_settings(_settings())
    require_step_up_header(req)
    assert req.state.ibex_step_up_ok is False


def _step_up_token(*, settings: Settings, org_id, subject: str, ttl: int = 300) -> str:
    return issue_token_opts(
        TokenIssueOpts(
            secret=settings.jwt_hmac_secret or "h" * 32,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            org_id=org_id,
            permissions=0,
            subject=subject,
            session_kind=SESSION_KIND_STEP_UP,
            ttl_seconds=ttl,
        )
    )


def test_step_up_header_valid_sets_true() -> None:
    settings = _settings()
    org = uuid4()
    token = issue_token_opts(
        TokenIssueOpts(
            secret=settings.jwt_hmac_secret or "h" * 32,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            org_id=org,
            permissions=SECRET_USE,
            subject="user-1",
            session_kind=SESSION_KIND_STEP_UP,
            ttl_seconds=300,
        )
    )
    req = _request_with_settings(settings, headers=[(b"x-ibex-step-up", token.encode())])
    req.state.ibex_session_org_id = org
    req.state.ibex_session_sub = "user-1"
    require_step_up_header(req)
    assert req.state.ibex_step_up_ok is True


def test_step_up_org_mismatch_denies() -> None:
    settings = _settings()
    token = _step_up_token(settings=settings, org_id=uuid4(), subject="user-1")
    req = _request_with_settings(settings, headers=[(b"x-ibex-step-up", token.encode())])
    req.state.ibex_session_org_id = uuid4()
    req.state.ibex_session_sub = "user-1"
    with pytest.raises(ApiError) as exc:
        require_step_up_header(req)
    assert exc.value.code == INSUFFICIENT_PERMISSIONS


def test_step_up_subject_mismatch_denies() -> None:
    settings = _settings()
    org = uuid4()
    token = _step_up_token(settings=settings, org_id=org, subject="user-1")
    req = _request_with_settings(settings, headers=[(b"x-ibex-step-up", token.encode())])
    req.state.ibex_session_org_id = org
    req.state.ibex_session_sub = "other-user"
    with pytest.raises(ApiError) as exc:
        require_step_up_header(req)
    assert exc.value.code == INSUFFICIENT_PERMISSIONS


def test_step_up_header_expired_denies() -> None:
    settings = _settings()
    token = _step_up_token(settings=settings, org_id=uuid4(), subject="user-1", ttl=-10)
    req = _request_with_settings(settings, headers=[(b"x-ibex-step-up", token.encode())])
    with pytest.raises(ApiError) as exc:
        require_step_up_header(req)
    assert exc.value.code == INSUFFICIENT_PERMISSIONS


def test_step_up_both_session_attrs_unset_denies() -> None:
    """Missing session binding is fail-closed — not a silent skip of org/sub checks."""
    settings = _settings()
    token = _step_up_token(settings=settings, org_id=uuid4(), subject="user-1")
    req = _request_with_settings(settings, headers=[(b"x-ibex-step-up", token.encode())])
    req.state.ibex_session_org_id = None
    req.state.ibex_session_sub = None
    with pytest.raises(ApiError) as exc:
        require_step_up_header(req)
    assert exc.value.code == INSUFFICIENT_PERMISSIONS
    assert getattr(req.state, "ibex_step_up_ok", False) is not True
