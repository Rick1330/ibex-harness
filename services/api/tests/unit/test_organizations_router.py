"""HTTP-level anti-enumeration and authz for org routes."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from authclient.permissions import ADMIN, READ_ONLY

from app.auth.client import ValidateResult
from app.authz import assert_path_org
from app.errors import ApiError
from app.schemas.organizations import OrganizationResponse, OrgDeletionJobResponse
from tests.unit.org_user_test_support import (
    api_client,
    managed_org_client,
    owner_result,
    override_org_session,
    sample_org_row,
)


def test_assert_path_org_anti_enumeration() -> None:
    try:
        assert_path_org(uuid4(), uuid4())
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.code == "NOT_FOUND"


def test_cross_tenant_org_get_returns_404() -> None:
    token_org = uuid4()
    other_org = uuid4()
    with api_client(result=owner_result(org_id=token_org)) as (client, _res, _pub):
        override_org_session(client.app)
        try:
            resp = client.get(
                f"/v1/organizations/{other_org}",
                headers={"Authorization": "Bearer owner-token"},
            )
        finally:
            client.app.dependency_overrides.clear()
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_get_org_happy_path() -> None:
    org_id = uuid4()
    row = sample_org_row(org_id)

    async def _fake_get(_session, oid):
        assert oid == org_id
        return OrganizationResponse(**row)

    with (
        managed_org_client(org_id=org_id, role="member") as (client, _res, _pub),
        patch("app.routers.organizations.org_service.get_organization", new=_fake_get),
    ):
        resp = client.get(
            f"/v1/organizations/{org_id}",
            headers={"Authorization": "Bearer owner-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == str(org_id)


def test_suspend_requires_owner_role_bitmap() -> None:
    org_id = uuid4()
    weak = ValidateResult(org_id=org_id, permissions=READ_ONLY, user_id=str(uuid4()))
    with managed_org_client(
        org_id=org_id, role="member", token="weak", result=weak
    ) as (client, _res, _pub):
        resp = client.post(
            f"/v1/organizations/{org_id}/suspend",
            headers={"Authorization": "Bearer weak"},
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_suspend_owner_publishes() -> None:
    org_id = uuid4()
    row = sample_org_row(org_id, status="suspended")

    async def _fake_suspend(session, oid, publisher):
        del session
        await publisher.publish_org_suspend(str(oid))
        return OrganizationResponse(**row)

    with (
        managed_org_client(org_id=org_id, role="owner") as (client, _res, pub),
        patch(
            "app.routers.organizations.org_service.suspend_organization",
            new=_fake_suspend,
        ),
    ):
        resp = client.post(
            f"/v1/organizations/{org_id}/suspend",
            headers={"Authorization": "Bearer owner-token"},
        )
        assert resp.status_code == 200
        assert pub.org_ids == [str(org_id)]


def test_delete_org_returns_202() -> None:
    org_id = uuid4()
    job_id = uuid4()

    async def _fake_enqueue(session, oid, *, enqueue_fn):
        del session
        enqueue_fn(str(job_id), str(oid))
        now = datetime.now(UTC)
        return OrgDeletionJobResponse(
            id=job_id,
            org_id=oid,
            status="pending",
            error=None,
            created_at=now,
            updated_at=now,
        )

    calls: list[tuple[str, str]] = []
    with (
        managed_org_client(org_id=org_id, role="owner", enqueue_calls=calls) as (
            client,
            _res,
            _pub,
        ),
        patch(
            "app.routers.organizations.org_service.enqueue_org_deletion",
            new=_fake_enqueue,
        ),
    ):
        resp = client.delete(
            f"/v1/organizations/{org_id}",
            headers={"Authorization": "Bearer owner-token"},
        )
        assert resp.status_code == 202
        assert resp.json()["status"] == "pending"
        assert calls == [(str(job_id), str(org_id))]


def test_member_cannot_patch_org() -> None:
    org_id = uuid4()
    member = ValidateResult(org_id=org_id, permissions=ADMIN, user_id=str(uuid4()))
    with managed_org_client(
        org_id=org_id, role="member", token="mem", result=member
    ) as (client, _res, _pub):
        resp = client.patch(
            f"/v1/organizations/{org_id}",
            headers={"Authorization": "Bearer mem"},
            json={"name": "Nope"},
        )
        assert resp.status_code == 403


def test_get_deletion_job() -> None:
    org_id = uuid4()
    job_id = uuid4()
    now = datetime.now(UTC)

    async def _fake_job(session, oid, jid):
        del session
        return OrgDeletionJobResponse(
            id=jid,
            org_id=oid,
            status="running",
            error=None,
            created_at=now,
            updated_at=now,
            started_at=now,
        )

    with (
        managed_org_client(org_id=org_id, role="owner") as (client, _res, _pub),
        patch("app.routers.organizations.org_service.get_deletion_job", new=_fake_job),
    ):
        resp = client.get(
            f"/v1/organizations/{org_id}/deletion-jobs/{job_id}",
            headers={"Authorization": "Bearer owner-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"


def test_patch_org_happy_path() -> None:
    org_id = uuid4()
    row = sample_org_row(org_id, name="Renamed")

    async def _fake_patch(session, oid, body):
        del session, body
        return OrganizationResponse(**row)

    with (
        managed_org_client(org_id=org_id, role="admin") as (client, _res, _pub),
        patch("app.routers.organizations.org_service.patch_organization", new=_fake_patch),
    ):
        resp = client.patch(
            f"/v1/organizations/{org_id}",
            headers={"Authorization": "Bearer owner-token"},
            json={"name": "Renamed"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"
