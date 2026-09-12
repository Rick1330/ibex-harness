"""Unit tests for model-policy CRUD routes (m4.C.2)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from apierror_py import INSUFFICIENT_PERMISSIONS, NOT_FOUND
from authclient.permissions import MEMORY_READ

from app.auth.client import ValidateResult
from app.model_policy_publish import RecordingModelPolicyPublisher
from app.pagination import CursorPage, PaginationMeta
from app.schemas.model_policies import ModelPolicyResponse
from tests.unit.org_user_test_support import (
    ManagedClientOpts,
    bearer_headers,
    managed_org_client,
    owner_result,
)


def _policy(org_id: UUID, **kwargs) -> ModelPolicyResponse:
    now = datetime.now(UTC)
    return ModelPolicyResponse(
        id=kwargs.get("id", uuid4()),
        org_id=org_id,
        model_pattern=kwargs.get("pattern", "claude-*"),
        allowed=kwargs.get("allowed", True),
        priority=kwargs.get("priority", 100),
        created_at=now,
        updated_at=now,
    )


def _page(org_id: UUID) -> CursorPage[ModelPolicyResponse]:
    return CursorPage(
        data=[_policy(org_id)],
        pagination=PaginationMeta(has_more=False),
    )


def _base(org_id: UUID) -> str:
    return f"/v1/organizations/{org_id}/model-policies"


def _mock_svc(name: str, value):
    return patch(f"app.services.model_policies.{name}", new=AsyncMock(return_value=value))


def test_list_model_policies_ok() -> None:
    org_id = uuid4()
    with (
        managed_org_client(ManagedClientOpts(org_id=org_id)) as (client, _, _),
        _mock_svc("list_policies", _page(org_id)),
    ):
        resp = client.get(_base(org_id), headers=bearer_headers())
    assert resp.status_code == 200
    assert resp.json()["data"][0]["model_pattern"] == "claude-*"


def test_create_model_policy_owner_ok() -> None:
    org_id = uuid4()
    pub = RecordingModelPolicyPublisher()
    with (
        managed_org_client(ManagedClientOpts(org_id=org_id)) as (client, _, _),
        _mock_svc("create_policy", _policy(org_id)) as patched,
    ):
        client.app.state.api.model_policy_publisher = pub
        resp = client.post(
            _base(org_id),
            headers=bearer_headers(),
            json={"model_pattern": "claude-*", "allowed": True, "priority": 10},
        )
    assert resp.status_code == 201
    assert patched.await_count == 1


def test_create_uses_noop_publisher_when_unset() -> None:
    org_id = uuid4()
    with (
        managed_org_client(ManagedClientOpts(org_id=org_id)) as (client, _, _),
        _mock_svc("create_policy", _policy(org_id)) as patched,
    ):
        client.app.state.api.model_policy_publisher = None
        resp = client.post(
            _base(org_id),
            headers=bearer_headers(),
            json={"model_pattern": "gpt-*", "allowed": True},
        )
    assert resp.status_code == 201
    assert patched.await_count == 1
    deps = patched.await_args.kwargs["deps"]
    assert deps.publisher is not None


def test_member_create_denied() -> None:
    org_id = uuid4()
    with managed_org_client(
        ManagedClientOpts(
            org_id=org_id,
            role="member",
            result=ValidateResult(
                org_id=org_id,
                permissions=MEMORY_READ,
                user_id=str(uuid4()),
            ),
        )
    ) as (client, _, _):
        resp = client.post(
            _base(org_id),
            headers=bearer_headers(),
            json={"model_pattern": "gpt-*", "allowed": False},
        )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == INSUFFICIENT_PERMISSIONS


def test_admin_patch_allowed() -> None:
    org_id = uuid4()
    policy_id = uuid4()
    with (
        managed_org_client(ManagedClientOpts(org_id=org_id, role="admin")) as (
            client,
            _,
            _,
        ),
        _mock_svc("patch_policy", _policy(org_id, id=policy_id, allowed=False)),
    ):
        resp = client.patch(
            f"{_base(org_id)}/{policy_id}",
            headers=bearer_headers(),
            json={"allowed": False},
        )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False


def test_delete_model_policy_ok() -> None:
    org_id = uuid4()
    policy_id = uuid4()
    with (
        managed_org_client(ManagedClientOpts(org_id=org_id)) as (client, _, _),
        _mock_svc("delete_policy", None),
    ):
        resp = client.delete(f"{_base(org_id)}/{policy_id}", headers=bearer_headers())
    assert resp.status_code == 204


def test_get_model_policy_ok() -> None:
    org_id = uuid4()
    policy_id = uuid4()
    with (
        managed_org_client(ManagedClientOpts(org_id=org_id)) as (client, _, _),
        _mock_svc("get_policy", _policy(org_id, id=policy_id)),
    ):
        resp = client.get(f"{_base(org_id)}/{policy_id}", headers=bearer_headers())
    assert resp.status_code == 200
    assert resp.json()["id"] == str(policy_id)


def test_invalid_glob_pattern_400() -> None:
    org_id = uuid4()
    with managed_org_client(ManagedClientOpts(org_id=org_id)) as (client, _, _):
        resp = client.post(
            _base(org_id),
            headers=bearer_headers(),
            json={"model_pattern": "bad[", "allowed": True},
        )
    assert resp.status_code == 400


def test_empty_character_class_glob_400() -> None:
    org_id = uuid4()
    with managed_org_client(ManagedClientOpts(org_id=org_id)) as (client, _, _):
        resp = client.post(
            _base(org_id),
            headers=bearer_headers(),
            json={"model_pattern": "[]", "allowed": True},
        )
    assert resp.status_code == 400


def test_unit_model_policies_list_foreign_org_404() -> None:
    _assert_foreign_org_404("GET")


def test_unit_model_policies_create_foreign_org_404() -> None:
    _assert_foreign_org_404("POST")


def test_unit_model_policies_get_foreign_org_404() -> None:
    _assert_foreign_org_404("GET_ONE")


def test_unit_model_policies_patch_foreign_org_404() -> None:
    _assert_foreign_org_404("PATCH")


def test_unit_model_policies_delete_foreign_org_404() -> None:
    _assert_foreign_org_404("DELETE")


def _assert_foreign_org_404(method: str) -> None:
    token_org = uuid4()
    foreign = uuid4()
    policy_id = uuid4()
    base = _base(foreign)
    with managed_org_client(
        ManagedClientOpts(org_id=token_org, result=owner_result(org_id=token_org))
    ) as (client, _, _):
        resp = _foreign_call(client, method, base, policy_id)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == NOT_FOUND


def _foreign_call(client, method: str, base: str, policy_id: UUID):
    headers = bearer_headers()
    if method == "GET":
        return client.get(base, headers=headers)
    if method == "POST":
        return client.post(
            base, headers=headers, json={"model_pattern": "x*", "allowed": True}
        )
    if method == "GET_ONE":
        return client.get(f"{base}/{policy_id}", headers=headers)
    if method == "PATCH":
        return client.patch(
            f"{base}/{policy_id}", headers=headers, json={"allowed": False}
        )
    return client.delete(f"{base}/{policy_id}", headers=headers)
