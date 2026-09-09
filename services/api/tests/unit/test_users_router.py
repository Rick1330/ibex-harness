"""HTTP tests for user invite/list/delete routes."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from authclient.permissions import ADMIN, READ_ONLY

from app.auth.client import ValidateResult
from app.pagination import CursorPage, PaginationMeta
from app.schemas.users import UserResponse
from tests.unit.org_user_test_support import (
    ManagedClientOpts,
    managed_org_client,
    sample_user_row,
)


def test_create_user_returns_invite_token_once() -> None:
    org_id = uuid4()
    row = sample_user_row(org_id, status="invited", role="member")

    async def _fake_create(session, oid, body, *, created_by):
        del session, created_by
        assert oid == org_id
        assert body.email == "new@example.com"
        return UserResponse(**row, invite_token="raw-invite-token")

    with (
        managed_org_client(ManagedClientOpts(org_id=org_id, role="admin")) as (client, _res, _pub),
        patch("app.routers.users.user_service.create_user_invite", new=_fake_create),
    ):
        resp = client.post(
            "/v1/users",
            headers={"Authorization": "Bearer owner-token"},
            json={"email": "new@example.com", "name": "New", "role": "member"},
        )
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

    with (
        managed_org_client(ManagedClientOpts(org_id=org_id, role="admin")) as (client, _res, _pub),
        patch("app.routers.users.user_service.list_users", new=_fake_list),
    ):
        resp = client.get("/v1/users", headers={"Authorization": "Bearer owner-token"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["pagination"]["has_more"] is False
    assert len(body["data"]) == 1


def test_member_cannot_list_users() -> None:
    org_id = uuid4()
    member = ValidateResult(org_id=org_id, permissions=ADMIN, user_id=str(uuid4()))
    with managed_org_client(
        ManagedClientOpts(org_id=org_id, role="member", token="mem", result=member)
    ) as (client, _res, _pub):
        resp = client.get("/v1/users", headers={"Authorization": "Bearer mem"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_viewer_cannot_get_user() -> None:
    org_id = uuid4()
    user_id = uuid4()
    viewer = ValidateResult(org_id=org_id, permissions=READ_ONLY, user_id=str(uuid4()))
    with managed_org_client(
        ManagedClientOpts(org_id=org_id, role="viewer", token="viewer", result=viewer)
    ) as (client, _res, _pub):
        resp = client.get(
            f"/v1/users/{user_id}",
            headers={"Authorization": "Bearer viewer"},
        )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_delete_user_204() -> None:
    org_id = uuid4()
    user_id = uuid4()

    async def _fake_delete(session, oid, uid, revoke):
        del session
        assert oid == org_id
        assert uid == user_id
        assert revoke.access_token

    with (
        managed_org_client(ManagedClientOpts(org_id=org_id, role="admin")) as (client, _res, _pub),
        patch("app.routers.users.user_service.soft_delete_user", new=_fake_delete),
    ):
        resp = client.delete(
            f"/v1/users/{user_id}",
            headers={"Authorization": "Bearer owner-token"},
        )
    assert resp.status_code == 204


def test_patch_user_route() -> None:
    org_id = uuid4()
    user_id = uuid4()
    row = sample_user_row(org_id, id=user_id, name="Patched")

    async def _fake_patch(session, oid, uid, body):
        del session, body
        assert oid == org_id
        assert uid == user_id
        return UserResponse(**row)

    with (
        managed_org_client(ManagedClientOpts(org_id=org_id, role="admin")) as (client, _res, _pub),
        patch("app.routers.users.user_service.patch_user", new=_fake_patch),
    ):
        resp = client.patch(
            f"/v1/users/{user_id}",
            headers={"Authorization": "Bearer owner-token"},
            json={"name": "Patched"},
        )
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

    with (
        managed_org_client(ManagedClientOpts(org_id=org_id, role="admin")) as (client, _res, _pub),
        patch("app.routers.users.user_service.get_user", new=_fake_get),
    ):
        resp = client.get(
            f"/v1/users/{user_id}",
            headers={"Authorization": "Bearer owner-token"},
        )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"
