"""Unit tests for last-owner protection and user service helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from apierror_py import LAST_OWNER_PROTECTED, NOT_FOUND
from sqlalchemy.exc import IntegrityError

from app.errors import ApiError
from app.schemas.users import UserCreate, UserPatch
from app.services import users as user_service


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value

    def mappings(self):
        return self

    def first(self):
        return self._value

    def all(self):
        return self._value if isinstance(self._value, list) else []

    def fetchall(self):
        if isinstance(self._value, list):
            return self._value
        if isinstance(self._value, int):
            return [object()] * self._value
        if self._value is None:
            return []
        return [self._value]


def _user(**overrides):
    now = datetime.now(UTC)
    base = {
        "id": uuid4(),
        "org_id": uuid4(),
        "email": "user@example.com",
        "name": "User",
        "role": "member",
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_assert_not_last_owner_blocks() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(1))
    with pytest.raises(ApiError) as exc:
        await user_service._assert_not_last_owner(session, uuid4())
    assert exc.value.code == LAST_OWNER_PROTECTED


@pytest.mark.asyncio
async def test_assert_not_last_owner_allows_when_multiple() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(2))
    await user_service._assert_not_last_owner(session, uuid4())


@pytest.mark.asyncio
async def test_get_user_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(None))
    with pytest.raises(ApiError) as exc:
        await user_service.get_user(session, uuid4(), uuid4())
    assert exc.value.code == NOT_FOUND


@pytest.mark.asyncio
async def test_patch_user_last_owner_demotion() -> None:
    org_id = uuid4()
    user_id = uuid4()
    current = _user(id=user_id, org_id=org_id, role="owner", email="owner@example.com")
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarResult(current), _ScalarResult(1)])
    patch = UserPatch(role="admin")
    with pytest.raises(ApiError) as exc:
        await user_service.patch_user(session, org_id, user_id, patch)
    assert exc.value.code == LAST_OWNER_PROTECTED


@pytest.mark.asyncio
async def test_patch_user_success() -> None:
    org_id = uuid4()
    user_id = uuid4()
    current = _user(id=user_id, org_id=org_id, role="member", name="Old")
    updated = _user(id=user_id, org_id=org_id, role="member", name="New")
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarResult(current), _ScalarResult(updated)])
    session.commit = AsyncMock()
    out = await user_service.patch_user(session, org_id, user_id, UserPatch(name="New"))
    assert out.name == "New"


@pytest.mark.asyncio
async def test_soft_delete_revokes_tokens() -> None:
    org_id = uuid4()
    user_id = uuid4()
    current = _user(id=user_id, org_id=org_id, role="member")
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _ScalarResult(current),
            _ScalarResult([SimpleNamespace(id="tok-1"), SimpleNamespace(id="tok-2")]),
            MagicMock(rowcount=1),
        ]
    )
    session.commit = AsyncMock()
    revoker = AsyncMock()
    await user_service.soft_delete_user(
        session,
        org_id,
        user_id,
        user_service.RevokeContext(revoker=revoker, access_token="secret"),
    )
    assert revoker.revoke.await_count == 2
    session.commit.assert_awaited()
    # Revokes complete before soft-delete commit.
    assert revoker.revoke.await_args_list[0].kwargs["token_id"] == "tok-1"


@pytest.mark.asyncio
async def test_soft_delete_auth_unavailable_skips_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    from authclient.errors import AuthUnavailableError

    org_id = uuid4()
    user_id = uuid4()
    current = _user(id=user_id, org_id=org_id, role="member")
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _ScalarResult(current),
            _ScalarResult([SimpleNamespace(id="tok-1")]),
        ]
    )
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    revoker = AsyncMock()
    revoker.revoke = AsyncMock(side_effect=AuthUnavailableError())
    monkeypatch.setattr(user_service.asyncio, "sleep", AsyncMock())

    with pytest.raises(AuthUnavailableError):
        await user_service.soft_delete_user(
            session,
            org_id,
            user_id,
            user_service.RevokeContext(revoker=revoker, access_token="secret"),
        )
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited()
    assert revoker.revoke.await_count == 3


@pytest.mark.asyncio
async def test_soft_delete_auth_unavailable_retries_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from authclient.errors import AuthUnavailableError

    org_id = uuid4()
    user_id = uuid4()
    current = _user(id=user_id, org_id=org_id, role="member")
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _ScalarResult(current),
            _ScalarResult([SimpleNamespace(id="tok-1")]),
            MagicMock(rowcount=1),
        ]
    )
    session.commit = AsyncMock()
    revoker = AsyncMock()
    revoker.revoke = AsyncMock(side_effect=[AuthUnavailableError(), None])
    monkeypatch.setattr(user_service.asyncio, "sleep", AsyncMock())

    await user_service.soft_delete_user(
        session,
        org_id,
        user_id,
        user_service.RevokeContext(revoker=revoker, access_token="secret"),
    )
    assert revoker.revoke.await_count == 2
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_list_users_first_page() -> None:
    org_id = uuid4()
    rows = [_user(org_id=org_id) for _ in range(3)]
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(rows))
    page = await user_service.list_users(session, org_id, cursor=None, limit=2)
    assert len(page.data) == 2
    assert page.pagination.has_more is True
    assert page.pagination.next_cursor is not None


@pytest.mark.asyncio
async def test_list_users_invalid_cursor() -> None:
    session = AsyncMock()
    with pytest.raises(ApiError):
        await user_service.list_users(session, uuid4(), cursor="%%%", limit=10)


@pytest.mark.asyncio
async def test_create_user_invite_integrity_error() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("unique")))
    session.rollback = AsyncMock()
    body = UserCreate(email="a@example.com", name="A", role="member")
    with pytest.raises(ApiError) as exc:
        await user_service.create_user_invite(session, uuid4(), body, created_by=None)
    assert "already exists" in exc.value.message


@pytest.mark.asyncio
async def test_list_users_with_cursor() -> None:
    from app.pagination import encode_cursor

    org_id = uuid4()
    rows = [_user(org_id=org_id)]
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(rows))
    cursor = encode_cursor({"created_at": "2026-01-01T00:00:00+00:00", "id": str(uuid4())})
    page = await user_service.list_users(session, org_id, cursor=cursor, limit=10)
    assert len(page.data) == 1


@pytest.mark.asyncio
async def test_soft_delete_last_owner_blocked() -> None:
    org_id = uuid4()
    user_id = uuid4()
    current = _user(id=user_id, org_id=org_id, role="owner")
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarResult(current), _ScalarResult(1)])
    revoke = user_service.RevokeContext(revoker=AsyncMock(), access_token="x")
    with pytest.raises(ApiError) as exc:
        await user_service.soft_delete_user(session, org_id, user_id, revoke)
    assert exc.value.code == LAST_OWNER_PROTECTED
