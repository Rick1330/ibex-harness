"""Unit tests for step-up header probe and operator authz deny-by-default."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

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


@dataclass(frozen=True)
class StepUpTokenSpec:
    org_id: UUID
    subject: str = "user-1"
    ttl: int = 300
    permissions: int = 0


def _step_up_token(settings: Settings, spec: StepUpTokenSpec) -> str:
    return issue_token_opts(
        TokenIssueOpts(
            secret=settings.jwt_hmac_secret or "h" * 32,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            org_id=spec.org_id,
            permissions=spec.permissions,
            subject=spec.subject,
            session_kind=SESSION_KIND_STEP_UP,
            ttl_seconds=spec.ttl,
        )
    )


def _step_up_request(
    settings: Settings,
    token: str,
    *,
    session_org: UUID | None | object = ...,
    session_sub: str | None | object = ...,
) -> Request:
    req = _request_with_settings(settings, headers=[(b"x-ibex-step-up", token.encode())])
    if session_org is not ...:
        req.state.ibex_session_org_id = session_org
    if session_sub is not ...:
        req.state.ibex_session_sub = session_sub
    return req


def _assert_step_up_denied(req: Request) -> None:
    with pytest.raises(ApiError) as exc:
        require_step_up_header(req)
    assert exc.value.code == INSUFFICIENT_PERMISSIONS
    assert getattr(req.state, "ibex_step_up_ok", False) is not True


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
    if want_code is None:
        with pytest.raises(ApiError) as exc:
            assert_operator_permission(settings, OPERATOR_RAW_READ, OPERATOR_RAW_READ)
        assert "Step-up" in exc.value.message
        return
    with pytest.raises(ApiError) as exc:
        assert_operator_permission(settings, OPERATOR_RAW_READ, OPERATOR_RAW_READ)
    assert exc.value.code == want_code


def test_assert_operator_permission_cannot_replace_step_up_dependency() -> None:
    settings = _settings()
    with pytest.raises(ApiError, match="Step-up"):
        assert_operator_permission(settings, OPERATOR_RAW_READ, OPERATOR_RAW_READ)


def test_assert_operator_permission_bitmap_missing() -> None:
    settings = _settings()
    with pytest.raises(ApiError) as exc:
        assert_operator_permission(settings, 0, OPERATOR_RAW_READ)
    assert exc.value.code == INSUFFICIENT_PERMISSIONS
    assert "Insufficient permissions" in exc.value.message


@pytest.mark.parametrize(
    ("settings_kw", "permissions", "expected_code"),
    [
        ({"operator_feature_enabled": False}, SECRET_USE, SERVICE_DEGRADED),
        ({"operator_allow_secret_use": False}, SECRET_USE, INSUFFICIENT_PERMISSIONS),
        ({}, 0, INSUFFICIENT_PERMISSIONS),
    ],
)
def test_require_operator_permission_denial_does_not_consume_step_up(
    settings_kw: dict[str, object], permissions: int, expected_code: str
) -> None:
    import asyncio
    from unittest.mock import AsyncMock, patch

    from app.auth.client import ValidateResult
    from app.authz import require_operator_permission

    token = ValidateResult(org_id=uuid4(), permissions=permissions, user_id="u1")
    dep = require_operator_permission(SECRET_USE)
    req = _request_with_settings(_settings(**settings_kw))
    pending = dep(req, token)
    with patch("app.authz.enforce_step_up", new=AsyncMock()) as enforce:
        with pytest.raises(ApiError) as exc:
            asyncio.run(pending)
    assert exc.value.code == expected_code
    enforce.assert_not_awaited()


def test_require_operator_permission_consumes_step_up_after_authorization() -> None:
    import asyncio
    from unittest.mock import AsyncMock, patch

    from app.auth.client import ValidateResult
    from app.authz import require_operator_permission

    token = ValidateResult(org_id=uuid4(), permissions=SECRET_USE, user_id="u1")
    req = _request_with_settings(_settings(operator_allow_secret_use=True))
    dep = require_operator_permission(SECRET_USE)
    with patch("app.authz.enforce_step_up", new=AsyncMock()) as enforce:
        result = asyncio.run(dep(req, token))
    assert result is token
    enforce.assert_awaited_once()


def test_step_up_header_missing_sets_false() -> None:
    req = _request_with_settings(_settings())
    require_step_up_header(req)
    assert req.state.ibex_step_up_ok is False


def test_step_up_header_valid_sets_true() -> None:
    settings = _settings()
    org = uuid4()
    token = _step_up_token(settings, StepUpTokenSpec(org, permissions=SECRET_USE))
    req = _step_up_request(settings, token, session_org=org, session_sub="user-1")
    require_step_up_header(req)
    assert req.state.ibex_step_up_ok is True


@pytest.mark.parametrize(
    "case",
    [
        "org_mismatch",
        "subject_mismatch",
        "expired",
        "both_attrs_unset",
    ],
)
def test_step_up_header_denies(case: str) -> None:
    settings = _settings()
    org = uuid4()
    if case == "org_mismatch":
        token = _step_up_token(settings, StepUpTokenSpec(uuid4()))
        req = _step_up_request(settings, token, session_org=uuid4(), session_sub="user-1")
    elif case == "subject_mismatch":
        token = _step_up_token(settings, StepUpTokenSpec(org))
        req = _step_up_request(settings, token, session_org=org, session_sub="other-user")
    elif case == "expired":
        token = _step_up_token(settings, StepUpTokenSpec(org, ttl=-10))
        req = _step_up_request(settings, token)
    else:
        token = _step_up_token(settings, StepUpTokenSpec(org))
        req = _step_up_request(settings, token, session_org=None, session_sub=None)
    _assert_step_up_denied(req)


@pytest.mark.parametrize(
    ("token_kwargs", "identity_kwargs"),
    [
        ({"org_id": uuid4()}, {}),
        ({"subject": "other-user"}, {}),
        ({"session_id": "other-session"}, {}),
        ({"action": "operator.permission.999"}, {}),
        ({"permissions": 0}, {}),
    ],
)
async def test_enforce_step_up_rejects_unbound_or_underprivileged_local_tokens(
    token_kwargs: dict[str, object], identity_kwargs: dict[str, object]
) -> None:
    from app.auth.client import ValidateResult
    from app.step_up import enforce_step_up

    org = uuid4()
    action = f"operator.permission.{SECRET_USE}"
    token_settings = _settings()
    values: dict[str, object] = {
        "org_id": org,
        "subject": "user-1",
        "session_id": "sid-1",
        "action": action,
        "permissions": SECRET_USE,
    }
    values.update(token_kwargs)
    claims = StepUpTokenSpec(
        org_id=values["org_id"],
        subject=str(values["subject"]),
        permissions=int(values["permissions"]),
    )
    raw = issue_token_opts(
        TokenIssueOpts(
            secret=token_settings.jwt_hmac_secret,
            issuer=token_settings.jwt_issuer,
            audience=token_settings.jwt_audience,
            org_id=claims.org_id,
            permissions=claims.permissions,
            subject=claims.subject,
            session_kind=SESSION_KIND_STEP_UP,
            ttl_seconds=300,
            session_id=str(values["session_id"]),
            action=str(values["action"]),
        )
    )
    req = _request_with_settings(token_settings, headers=[(b"x-ibex-step-up", raw.encode())])
    req.state.ibex_session_id = "sid-1"
    identity = {"org_id": org, "permissions": SECRET_USE, "user_id": "user-1"}
    identity.update(identity_kwargs)
    caller = ValidateResult(**identity)

    with pytest.raises(ApiError) as exc:
        await enforce_step_up(req, caller, required_permission=SECRET_USE, action=action)
    assert exc.value.code == INSUFFICIENT_PERMISSIONS
    assert exc.value.message == "Step-up authentication required"


def test_enforce_step_up_rejects_missing_header_and_missing_identity() -> None:
    import asyncio

    from app.auth.client import ValidateResult
    from app.step_up import enforce_step_up

    req = _request_with_settings(_settings())
    caller = ValidateResult(org_id=uuid4(), permissions=SECRET_USE)
    missing_header = enforce_step_up(
        req, caller, required_permission=SECRET_USE, action="op"
    )
    with pytest.raises(ApiError) as exc:
        asyncio.run(missing_header)
    assert exc.value.code == INSUFFICIENT_PERMISSIONS
    assert exc.value.message == "Step-up authentication required"

    req = _request_with_settings(_settings(), headers=[(b"x-ibex-step-up", b"untrusted")])
    missing_identity = ValidateResult(org_id=uuid4(), permissions=SECRET_USE)
    unbound = enforce_step_up(
        req, missing_identity, required_permission=SECRET_USE, action="op"
    )
    with pytest.raises(ApiError) as exc:
        asyncio.run(unbound)
    assert exc.value.code == INSUFFICIENT_PERMISSIONS


@pytest.mark.parametrize(
    ("rpc_error", "expected_code"),
    [
        (None, None),
        ("invalid", INSUFFICIENT_PERMISSIONS),
        ("unavailable", SERVICE_DEGRADED),
    ],
)
def test_enforce_step_up_uses_authservice_in_non_development(
    rpc_error: str | None, expected_code: str | None
) -> None:
    import asyncio
    from unittest.mock import AsyncMock, patch

    from app.auth.client import ValidateResult
    from app.auth.errors import AuthFailedError, AuthUnavailableError
    from app.step_up import enforce_step_up

    error = {
        "invalid": AuthFailedError("invalid"),
        "unavailable": AuthUnavailableError("down"),
    }.get(rpc_error)
    settings = _settings(
        environment="staging",
        jwt_hmac_secret=None,
        jwt_public_keys_pem="configured-public-key",
        auth_timeout_ms=50,
    )
    req = _request_with_settings(settings, headers=[(b"x-ibex-step-up", b"opaque-proof")])
    req.state.ibex_session_id = "sid-1"
    caller = ValidateResult(org_id=uuid4(), permissions=SECRET_USE, user_id="user-1")
    consume = AsyncMock(side_effect=error)

    async def enforce() -> None:
        await enforce_step_up(
            req,
            caller,
            required_permission=SECRET_USE,
            action=f"operator.permission.{SECRET_USE}",
        )

    with patch("app.step_up.consume_step_up", new=consume):
        if expected_code is None:
            asyncio.run(enforce())
            assert req.state.ibex_step_up_ok is True
        else:
            pending = enforce()
            with pytest.raises(ApiError) as exc:
                asyncio.run(pending)
            assert exc.value.code == expected_code
    assert consume.await_count == 1
    assert consume.await_args.kwargs["subject"] == "user-1"
    assert consume.await_args.kwargs["session_id"] == "sid-1"
    assert consume.await_args.kwargs["action"] == f"operator.permission.{SECRET_USE}"
    assert consume.await_args.kwargs["permission"] == SECRET_USE
