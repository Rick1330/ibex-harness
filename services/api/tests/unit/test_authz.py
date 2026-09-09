"""Unit tests for role + bitmap authz helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from apierror_py import INSUFFICIENT_PERMISSIONS, NOT_FOUND
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
