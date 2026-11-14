"""Unit tests for model-policy CRUD routes (m4.C.2)."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from apierror_py import INSUFFICIENT_PERMISSIONS, NOT_FOUND
from authclient.permissions import MEMORY_READ, OPERATOR_METADATA_READ, READ_ONLY

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


@dataclass(frozen=True)
class _SinglePolicyCall:
    """One single-policy route call: HTTP verb and the stubbed service method."""

    verb: str
    service: str


def _call_single_policy(call: _SinglePolicyCall):
    org_id = uuid4()
    policy_id = uuid4()
    value = _policy(org_id, id=policy_id) if call.verb == "get" else None
    with (
        managed_org_client(ManagedClientOpts(org_id=org_id)) as (client, _, _),
        _mock_svc(call.service, value),
    ):
        resp = getattr(client, call.verb)(f"{_base(org_id)}/{policy_id}", headers=bearer_headers())
    return resp, policy_id


def test_delete_model_policy_ok() -> None:
    resp, _policy_id = _call_single_policy(_SinglePolicyCall("delete", "delete_policy"))
    assert resp.status_code == 204


def test_get_model_policy_ok() -> None:
    resp, policy_id = _call_single_policy(_SinglePolicyCall("get", "get_policy"))
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


def _result(org_id: UUID, permissions: int) -> ValidateResult:
    return ValidateResult(
        org_id=org_id,
        permissions=permissions,
        user_id=str(uuid4()),
    )


@dataclass(frozen=True)
class _PolicyRead:
    """One model-policy read: collection or single, permission bitmap, gate state."""

    single: bool
    permissions: int = OPERATOR_METADATA_READ
    operator_feature_enabled: bool = True
    stub_service: bool = True


def _policy_read_response(case: _PolicyRead):
    org_id = uuid4()
    policy_id = uuid4()
    if case.single:
        target, value = "get_policy", _policy(org_id, id=policy_id)
        path = f"{_base(org_id)}/{policy_id}"
    else:
        target, value = "list_policies", _page(org_id)
        path = _base(org_id)
    opts = ManagedClientOpts(org_id=org_id, result=_result(org_id, case.permissions))
    with ExitStack() as stack:
        client, _res, _pub = stack.enter_context(managed_org_client(opts))
        if case.stub_service:
            stack.enter_context(_mock_svc(target, value))
        client.app.state.settings.operator_feature_enabled = case.operator_feature_enabled
        return client.get(path, headers=bearer_headers())


def _assert_policy_read_allowed(case: _PolicyRead) -> None:
    assert _policy_read_response(case).status_code == 200


def _assert_policy_read_denied(case: _PolicyRead) -> None:
    resp = _policy_read_response(case)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == INSUFFICIENT_PERMISSIONS


@pytest.mark.parametrize("single", [False, True])
def test_read_model_policies_deny_viewer_bitmap(single: bool) -> None:
    _assert_policy_read_denied(
        _PolicyRead(single=single, permissions=READ_ONLY, stub_service=False)
    )


@pytest.mark.parametrize("single", [False, True])
def test_read_model_policies_with_operator_metadata_read(single: bool) -> None:
    _assert_policy_read_allowed(_PolicyRead(single=single))


@pytest.mark.parametrize("single", [False, True])
def test_read_model_policies_survive_disabled_operator_feature(single: bool) -> None:
    """The operator feature gate covers the operator surface, not these org reads."""
    _assert_policy_read_allowed(_PolicyRead(single=single, operator_feature_enabled=False))


@pytest.mark.parametrize("single", [False, True])
def test_read_model_policies_deny_missing_bit_with_operator_disabled(
    single: bool,
) -> None:
    _assert_policy_read_denied(
        _PolicyRead(
            single=single,
            permissions=READ_ONLY,
            operator_feature_enabled=False,
            stub_service=False,
        )
    )
