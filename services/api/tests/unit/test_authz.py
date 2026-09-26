"""Unit tests for role + bitmap authz helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from apierror_py import INSUFFICIENT_PERMISSIONS, NOT_FOUND, SERVICE_DEGRADED
from authclient.permissions import ADMIN, READ_ONLY, USER_MANAGE

from app.auth.client import ValidateResult
from app.authz import load_caller_role, require_roles
from app.errors import ApiError


class _RoleResult:
    def __init__(self, role):
        self._role = role

    def scalar_one_or_none(self):
        return self._role


@pytest.mark.asyncio
async def test_load_caller_role_requires_user_id() -> None:
    token = ValidateResult(org_id=uuid4(), permissions=ADMIN, user_id=None)
    session = AsyncMock()
    with pytest.raises(ApiError) as exc:
        await load_caller_role(token, session)
    assert exc.value.code == INSUFFICIENT_PERMISSIONS


@pytest.mark.asyncio
async def test_load_caller_role_missing_user() -> None:
    token = ValidateResult(org_id=uuid4(), permissions=ADMIN, user_id=str(uuid4()))
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_RoleResult(None))
    with pytest.raises(ApiError) as exc:
        await load_caller_role(token, session)
    assert exc.value.code == NOT_FOUND


@pytest.mark.asyncio
async def test_load_caller_role_ok() -> None:
    token = ValidateResult(org_id=uuid4(), permissions=ADMIN, user_id=str(uuid4()))
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_RoleResult("admin"))
    assert await load_caller_role(token, session) == "admin"


@pytest.mark.asyncio
async def test_operator_legal_hold_role_session_closes_before_step_up() -> None:
    from authclient.permissions import LEGAL_HOLD_MANAGE, bitmap_for_role

    from app.authz import require_operator_legal_hold_manage
    from app.operator_session_auth import OperatorSessionAuthorization

    class _RoleSession:
        def __init__(self) -> None:
            self.closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args: object) -> None:
            self.closed = True

        async def execute(self, *_args: object):
            return _RoleResult("admin")

    session = _RoleSession()
    operator = OperatorSessionAuthorization(
        org_id=uuid4(),
        permissions=bitmap_for_role("admin"),
        session_id="session-1",
        subject="user-1",
    )
    step_up = AsyncMock()
    request = MagicMock()
    dep = require_operator_legal_hold_manage()
    with (
        patch("app.authz.session_with_org", return_value=session) as bind,
        patch("app.authz.enforce_step_up", new=step_up) as enforce,
    ):
        result = await dep(request, operator, object())
    assert result is operator
    bind.assert_called_once()
    assert session.closed is True
    enforce.assert_awaited_once()
    action = enforce.await_args.kwargs["action"]
    assert action.required_permission == LEGAL_HOLD_MANAGE
    assert action.session_id == "session-1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "permissions"),
    [("member", "admin"), ("admin", "member")],
)
async def test_operator_legal_hold_denies_before_step_up(
    role: str, permissions: str
) -> None:
    from authclient.permissions import bitmap_for_role

    from app.authz import require_operator_legal_hold_manage
    from app.operator_session_auth import OperatorSessionAuthorization

    class _RoleSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def execute(self, *_args: object):
            return _RoleResult(role)

    operator = OperatorSessionAuthorization(
        org_id=uuid4(),
        permissions=bitmap_for_role(permissions),
        session_id="session-1",
        subject="user-1",
    )
    pending = require_operator_legal_hold_manage()(MagicMock(), operator, object())
    with (
        patch("app.authz.session_with_org", return_value=_RoleSession()),
        patch("app.authz.enforce_step_up", new=AsyncMock()) as enforce,
        pytest.raises(ApiError) as exc,
    ):
        await pending
    assert exc.value.code == INSUFFICIENT_PERMISSIONS
    enforce.assert_not_awaited()


def test_require_roles_permission_gate() -> None:
    dep = require_roles(frozenset({"admin"}), required_permission=USER_MANAGE)
    token = ValidateResult(org_id=uuid4(), permissions=READ_ONLY, user_id=str(uuid4()))
    with pytest.raises(ApiError) as exc:
        dep(token=token, role="admin")
    assert exc.value.code == INSUFFICIENT_PERMISSIONS


def test_require_roles_ok() -> None:
    dep = require_roles(frozenset({"admin"}), required_permission=USER_MANAGE)
    token = ValidateResult(org_id=uuid4(), permissions=ADMIN, user_id=str(uuid4()))
    assert dep(token=token, role="admin") is token


def test_require_roles_role_gate() -> None:
    dep = require_roles(frozenset({"admin"}), required_permission=USER_MANAGE)
    token = ValidateResult(org_id=uuid4(), permissions=ADMIN, user_id=str(uuid4()))
    with pytest.raises(ApiError) as exc:
        dep(token=token, role="member")
    assert exc.value.code == INSUFFICIENT_PERMISSIONS


def test_assert_path_org_mismatch() -> None:
    from app.authz import assert_path_org

    org = uuid4()
    with pytest.raises(ApiError) as exc:
        assert_path_org(org, uuid4())
    assert exc.value.code == NOT_FOUND
    assert_path_org(org, org)


def test_require_legal_hold_manage_step_up() -> None:
    import asyncio
    from unittest.mock import MagicMock

    from authclient.permissions import LEGAL_HOLD_MANAGE, bitmap_for_role

    from app.authz import require_legal_hold_manage

    dep = require_legal_hold_manage()
    org = uuid4()
    token = ValidateResult(
        org_id=org,
        permissions=bitmap_for_role("admin"),
        user_id=str(uuid4()),
    )
    request = MagicMock()
    request.state.ibex_step_up_ok = False
    missing_step_up = dep(request=request, token=token)
    with pytest.raises(ApiError) as exc:
        asyncio.run(missing_step_up)
    assert exc.value.code == INSUFFICIENT_PERMISSIONS

    request.state.ibex_step_up_ok = True
    with_step_up = dep(request=request, token=token)
    with pytest.raises(ApiError):
        asyncio.run(with_step_up)
    assert LEGAL_HOLD_MANAGE


def test_assert_operator_permission_gates() -> None:
    from unittest.mock import MagicMock

    from authclient.permissions import OPERATOR_DELETE

    from app.authz import assert_operator_permission

    settings = MagicMock(operator_feature_enabled=False)
    with pytest.raises(ApiError) as exc:
        assert_operator_permission(settings, OPERATOR_DELETE, OPERATOR_DELETE)
    assert exc.value.code == SERVICE_DEGRADED

    settings = MagicMock(
        operator_feature_enabled=True,
        operator_allow_delete=False,
    )
    with pytest.raises(ApiError) as exc:
        assert_operator_permission(settings, OPERATOR_DELETE, OPERATOR_DELETE)
    assert exc.value.code == INSUFFICIENT_PERMISSIONS

    settings = MagicMock(
        operator_feature_enabled=True,
        operator_allow_delete=True,
    )
    with pytest.raises(ApiError) as exc:
        assert_operator_permission(settings, 0, OPERATOR_DELETE)
    assert exc.value.code == INSUFFICIENT_PERMISSIONS

    with pytest.raises(ApiError) as exc:
        assert_operator_permission(settings, OPERATOR_DELETE, OPERATOR_DELETE)
    assert exc.value.code == INSUFFICIENT_PERMISSIONS


def test_maybe_operator_session_returns_none_without_step_up_header() -> None:
    import asyncio
    from unittest.mock import MagicMock

    from app.authz import _maybe_operator_session

    request = MagicMock()
    request.headers.get.return_value = None
    assert asyncio.run(_maybe_operator_session(request)) is None
    request.headers.get.assert_called_once_with("X-IBEX-Step-Up")


def test_maybe_operator_session_delegates_when_step_up_header_present() -> None:
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch
    from uuid import uuid4

    from app.authz import _maybe_operator_session
    from app.operator_session_auth import OperatorSessionAuthorization

    request = MagicMock()
    request.headers.get.return_value = "proof"
    expected = OperatorSessionAuthorization(org_id=uuid4(), permissions=1, session_id="sid")
    with patch("app.authz.require_operator_session", new=AsyncMock(return_value=expected)) as require:
        got = asyncio.run(_maybe_operator_session(request))
    assert got is expected
    require.assert_awaited_once_with(request)


def test_assert_operator_permission_kill_switches() -> None:
    from unittest.mock import MagicMock

    from apierror_py import INSUFFICIENT_PERMISSIONS
    from authclient.permissions import (
        OPERATOR_EXPORT,
        OPERATOR_RAW_READ,
        OPERATOR_REPLAY,
        SECRET_USE,
    )

    from app.authz import assert_operator_permission
    from app.errors import ApiError

    cases = [
        ({"operator_allow_export": False}, OPERATOR_EXPORT),
        ({"operator_allow_replay": False}, OPERATOR_REPLAY),
        ({"operator_allow_raw_read": False}, OPERATOR_RAW_READ),
        ({"operator_allow_secret_use": False}, SECRET_USE),
    ]
    for kw, perm in cases:
        settings = MagicMock(operator_feature_enabled=True, **kw)
        for attr in (
            "operator_allow_export",
            "operator_allow_replay",
            "operator_allow_raw_read",
            "operator_allow_secret_use",
            "operator_allow_delete",
        ):
            if attr not in kw:
                setattr(settings, attr, True)
        with pytest.raises(ApiError) as exc:
            assert_operator_permission(settings, perm, perm)
        assert exc.value.code == INSUFFICIENT_PERMISSIONS
