"""HTTP tests for user invite/list/delete routes."""

from __future__ import annotations

from uuid import uuid4

import pytest
from authclient.permissions import ADMIN, READ_ONLY

from app.auth.client import ValidateResult
from app.pagination import CursorPage, PaginationMeta
from app.schemas.users import UserResponse
from tests.unit.org_user_test_support import (
    ManagedClientOpts,
    bearer_headers,
    managed_org_client,
    patched_managed_client,
    sample_user_row,
)


@pytest.mark.parametrize(
    "case",
    [
        ("member", "mem", ADMIN, "get", "/v1/users"),
        ("viewer", "viewer", READ_ONLY, "get", None),
    ],
)
def test_user_reads_denied_without_manage(case: tuple) -> None:
    role, token, perms, method, path = case
    org_id = uuid4()
    result = ValidateResult(org_id=org_id, permissions=perms, user_id=str(uuid4()))
    target = path or f"/v1/users/{uuid4()}"
    with managed_org_client(
        ManagedClientOpts(org_id=org_id, role=role, token=token, result=result)
    ) as (client, _res, _pub):
        resp = getattr(client, method)(target, headers=bearer_headers(token))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_create_and_list_users() -> None:
    org_id = uuid4()
    invited = sample_user_row(org_id, status="invited", role="member")
    listed = UserResponse(**sample_user_row(org_id))

    async def _fake_create(session, oid, body, *, created_by):
        del session, created_by
        assert oid == org_id
        assert body.email == "new@example.com"
        return UserResponse(**invited, invite_token="raw-invite-token")

    async def _fake_list(session, oid, *, cursor, limit):
        del session, cursor
        assert oid == org_id
        assert limit == 50
        return CursorPage(
            data=[listed],
            pagination=PaginationMeta(has_more=False, next_cursor=None),
        )

    with patched_managed_client(
        ManagedClientOpts(org_id=org_id, role="admin"),
        "app.routers.users.user_service.create_user_invite",
        _fake_create,
    ) as (client, _res, _pub):
        created = client.post(
            "/v1/users",
            headers=bearer_headers(),
            json={"email": "new@example.com", "name": "New", "role": "member"},
        )
    assert created.status_code == 201
    assert created.json()["invite_token"] == "raw-invite-token"

    with patched_managed_client(
        ManagedClientOpts(org_id=org_id, role="admin"),
        "app.routers.users.user_service.list_users",
        _fake_list,
    ) as (client, _res, _pub):
        page = client.get("/v1/users", headers=bearer_headers())
    assert page.status_code == 200
    assert len(page.json()["data"]) == 1


def test_patch_get_delete_user_routes() -> None:
    org_id = uuid4()
    user_id = uuid4()
    row = sample_user_row(org_id, id=user_id, name="Patched")

    async def _fake_patch(session, args):
        del session
        assert args.org_id == org_id
        assert args.user_id == user_id
        return UserResponse(**row)

    async def _fake_get(session, oid, uid):
        del session, oid, uid
        from apierror_py import NOT_FOUND

        from app.errors import ApiError

        raise ApiError(code=NOT_FOUND, message="User not found")

    async def _fake_delete(session, oid, uid, revoke):
        del session
        assert oid == org_id
        assert uid == user_id
        assert revoke.access_token

    with patched_managed_client(
        ManagedClientOpts(org_id=org_id, role="admin"),
        "app.routers.users.user_service.patch_user",
        _fake_patch,
    ) as (client, _res, _pub):
        patched = client.patch(
            f"/v1/users/{user_id}",
            headers=bearer_headers(),
            json={"name": "Patched"},
        )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Patched"

    with patched_managed_client(
        ManagedClientOpts(org_id=org_id, role="admin"),
        "app.routers.users.user_service.get_user",
        _fake_get,
    ) as (client, _res, _pub):
        missing = client.get(f"/v1/users/{user_id}", headers=bearer_headers())
    assert missing.status_code == 404

    with patched_managed_client(
        ManagedClientOpts(org_id=org_id, role="admin"),
        "app.routers.users.user_service.soft_delete_user",
        _fake_delete,
    ) as (client, _res, _pub):
        deleted = client.delete(f"/v1/users/{user_id}", headers=bearer_headers())
    assert deleted.status_code == 204
