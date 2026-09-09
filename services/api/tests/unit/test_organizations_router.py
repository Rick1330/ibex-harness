"""HTTP-level anti-enumeration and authz for org routes."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from authclient.permissions import ADMIN, READ_ONLY

from app.auth.client import ValidateResult
from app.authz import assert_path_org
from app.errors import ApiError
from app.schemas.organizations import OrganizationResponse, OrgDeletionJobResponse
from tests.unit.org_user_test_support import (
    ManagedClientOpts,
    api_client,
    bearer_headers,
    managed_org_client,
    override_org_session,
    owner_result,
    patched_managed_client,
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
            resp = client.get(f"/v1/organizations/{other_org}", headers=bearer_headers())
        finally:
            client.app.dependency_overrides.clear()
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    "case",
    [
        ("member", "weak", READ_ONLY, "post", "/suspend", None),
        ("member", "mem", ADMIN, "patch", "", {"name": "Nope"}),
    ],
)
def test_org_mutations_denied_for_non_owners(case: tuple) -> None:
    role, token, perms, method, path_suffix, json_body = case
    org_id = uuid4()
    result = ValidateResult(org_id=org_id, permissions=perms, user_id=str(uuid4()))
    with managed_org_client(
        ManagedClientOpts(org_id=org_id, role=role, token=token, result=result)
    ) as (client, _res, _pub):
        call = getattr(client, method)
        kwargs: dict = {"headers": bearer_headers(token)}
        if json_body is not None:
            kwargs["json"] = json_body
        resp = call(f"/v1/organizations/{org_id}{path_suffix}", **kwargs)
    assert resp.status_code == 403


def test_get_and_patch_org_happy_paths() -> None:
    org_id = uuid4()
    get_row = sample_org_row(org_id)
    patch_row = sample_org_row(org_id, name="Renamed")

    async def _fake_get(_session, oid):
        assert oid == org_id
        return OrganizationResponse(**get_row)

    async def _fake_patch(session, oid, body):
        del session, body
        return OrganizationResponse(**patch_row)

    with patched_managed_client(
        ManagedClientOpts(org_id=org_id, role="member"),
        "app.routers.organizations.org_service.get_organization",
        _fake_get,
    ) as (client, _res, _pub):
        got = client.get(f"/v1/organizations/{org_id}", headers=bearer_headers())
    assert got.status_code == 200
    assert got.json()["id"] == str(org_id)

    with patched_managed_client(
        ManagedClientOpts(org_id=org_id, role="admin"),
        "app.routers.organizations.org_service.patch_organization",
        _fake_patch,
    ) as (client, _res, _pub):
        patched = client.patch(
            f"/v1/organizations/{org_id}",
            headers=bearer_headers(),
            json={"name": "Renamed"},
        )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Renamed"


def test_suspend_owner_publishes() -> None:
    org_id = uuid4()
    row = sample_org_row(org_id, status="suspended")

    async def _fake_suspend(session, oid, publisher):
        del session
        await publisher.publish_org_suspend(str(oid))
        return OrganizationResponse(**row)

    with patched_managed_client(
        ManagedClientOpts(org_id=org_id, role="owner"),
        "app.routers.organizations.org_service.suspend_organization",
        _fake_suspend,
    ) as (client, _res, pub):
        resp = client.post(f"/v1/organizations/{org_id}/suspend", headers=bearer_headers())
    assert resp.status_code == 200
    assert pub.org_ids == [str(org_id)]


def test_delete_org_and_job_lookup() -> None:
    org_id = uuid4()
    job_id = uuid4()
    now = datetime.now(UTC)
    calls: list[tuple[str, str]] = []

    async def _fake_enqueue(session, oid, *, enqueue_fn):
        del session
        enqueue_fn(str(job_id), str(oid))
        return OrgDeletionJobResponse(
            id=job_id,
            org_id=oid,
            status="pending",
            error=None,
            created_at=now,
            updated_at=now,
        )

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

    with patched_managed_client(
        ManagedClientOpts(org_id=org_id, role="owner", enqueue_calls=calls),
        "app.routers.organizations.org_service.enqueue_org_deletion",
        _fake_enqueue,
    ) as (client, _res, _pub):
        deleted = client.delete(f"/v1/organizations/{org_id}", headers=bearer_headers())
    assert deleted.status_code == 202
    assert deleted.json()["status"] == "pending"
    assert calls == [(str(job_id), str(org_id))]

    with patched_managed_client(
        ManagedClientOpts(org_id=org_id, role="owner"),
        "app.routers.organizations.org_service.get_deletion_job",
        _fake_job,
    ) as (client, _res, _pub):
        job = client.get(
            f"/v1/organizations/{org_id}/deletion-jobs/{job_id}",
            headers=bearer_headers(),
        )
    assert job.status_code == 200
    assert job.json()["status"] == "running"
