"""HTTP tests for user invite/list/delete routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.pagination import CursorPage, PaginationMeta
from app.schemas.users import UserResponse
from tests.unit.org_user_test_support import api_client, owner_result, sample_user_row


def test_create_user_returns_invite_token_once() -> None:
    org_id = uuid4()
    row = sample_user_row(org_id, status="invited", role="member")

    async def _fake_create(session, oid, body, *, created_by):
        del session, created_by
        assert oid == org_id
        assert body.email == "new@example.com"
        return UserResponse(**row, invite_token="raw-invite-token")

    with api_client(result=owner_result(org_id=org_id)) as (client, _res, _pub):
        app = client.app

        async def _session_override():
            yield AsyncMock()

        from app.authz import load_caller_role
        from app.deps import org_session

        async def _role_override():
            return "admin"

        app.dependency_overrides[org_session] = _session_override
        app.dependency_overrides[load_caller_role] = _role_override
        with patch("app.routers.users.user_service.create_user_invite", new=_fake_create):
            try:
                resp = client.post(
                    "/v1/users",
                    headers={"Authorization": "Bearer owner-token"},
                    json={"email": "new@example.com", "name": "New", "role": "member"},
                )
            finally:
                app.dependency_overrides.clear()
        assert resp.status_code == 201
        body = resp.json()
        assert body["invite_token"] == "raw-invite-token"
        assert body["status"] == "invited"


def test_list_users_returns_cursor_page() -> None:
    org_id = uuid4()
    user = UserResponse(**sample_user_row(org_id))

    async def _fake_list(session, oid, *, cursor, limit):
        del session, cursor
        assert oid == org_id
        assert limit == 50
        return CursorPage(
            data=[user],
            pagination=PaginationMeta(has_more=False, next_cursor=None),
        )

    with api_client(result=owner_result(org_id=org_id)) as (client, _res, _pub):
        app = client.app

        async def _session_override():
            yield AsyncMock()

        from app.deps import org_session

        app.dependency_overrides[org_session] = _session_override
        with patch("app.routers.users.user_service.list_users", new=_fake_list):
            try:
                resp = client.get(
                    "/v1/users",
                    headers={"Authorization": "Bearer owner-token"},
                )
            finally:
                app.dependency_overrides.clear()
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["has_more"] is False
        assert len(body["data"]) == 1


def test_delete_user_204() -> None:
    org_id = uuid4()
    user_id = uuid4()

    async def _fake_delete(session, oid, uid, revoke):
        del session
        assert oid == org_id
        assert uid == user_id
        assert revoke.access_token

    with api_client(result=owner_result(org_id=org_id)) as (client, _res, _pub):
        app = client.app

        async def _session_override():
            yield AsyncMock()

        from app.authz import load_caller_role
        from app.deps import org_session

        async def _role_override():
            return "admin"

        app.dependency_overrides[org_session] = _session_override
        app.dependency_overrides[load_caller_role] = _role_override
        with patch("app.routers.users.user_service.soft_delete_user", new=_fake_delete):
            try:
                resp = client.delete(
                    f"/v1/users/{user_id}",
                    headers={"Authorization": "Bearer owner-token"},
                )
            finally:
                app.dependency_overrides.clear()
        assert resp.status_code == 204


def test_patch_user_route() -> None:
    org_id = uuid4()
    user_id = uuid4()
    row = sample_user_row(org_id, id=user_id, name="Patched")

    async def _fake_patch(session, oid, uid, body):
        del session, body
        assert oid == org_id and uid == user_id
        return UserResponse(**row)

    with api_client(result=owner_result(org_id=org_id)) as (client, _res, _pub):
        app = client.app

        async def _session_override():
            yield AsyncMock()

        from app.authz import load_caller_role
        from app.deps import org_session

        async def _role_override():
            return "admin"

        app.dependency_overrides[org_session] = _session_override
        app.dependency_overrides[load_caller_role] = _role_override
        with patch("app.routers.users.user_service.patch_user", new=_fake_patch):
            try:
                resp = client.patch(
                    f"/v1/users/{user_id}",
                    headers={"Authorization": "Bearer owner-token"},
                    json={"name": "Patched"},
                )
            finally:
                app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert resp.json()["name"] == "Patched"


def test_get_user_not_found_envelope() -> None:
    org_id = uuid4()
    user_id = uuid4()

    async def _fake_get(session, oid, uid):
        del session, oid, uid
        from apierror_py import NOT_FOUND

        from app.errors import ApiError

        raise ApiError(code=NOT_FOUND, message="User not found")

    with api_client(result=owner_result(org_id=org_id)) as (client, _res, _pub):
        app = client.app

        async def _session_override():
            yield AsyncMock()

        from app.deps import org_session

        app.dependency_overrides[org_session] = _session_override
        with patch("app.routers.users.user_service.get_user", new=_fake_get):
            try:
                resp = client.get(
                    f"/v1/users/{user_id}",
                    headers={"Authorization": "Bearer owner-token"},
                )
            finally:
                app.dependency_overrides.clear()
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"
