"""Unit tests for rate-limit configuration routes (m4.B.2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from apierror_py import INSUFFICIENT_PERMISSIONS, NOT_FOUND
from authclient.permissions import MEMORY_READ

from app.auth.client import ValidateResult
from app.rate_limit_publish import RecordingRateLimitConfigPublisher
from app.schemas.rate_limits import RateLimitsResponse
from tests.unit.org_user_test_support import (
    ManagedClientOpts,
    bearer_headers,
    managed_org_client,
    owner_result,
)


def _response(org_id: UUID, **kwargs) -> RateLimitsResponse:
    return RateLimitsResponse(
        org_id=org_id,
        requests_per_minute=kwargs.get("rpm", 60),
        source=kwargs.get("source", "default"),
        platform_default_rpm=60,
        current_minute_requests=kwargs.get("current", 0),
        agent_overrides=[],
    )


def _mock_service(name: str, org_id: UUID, **kwargs):
    return patch(
        f"app.services.rate_limits.{name}",
        new=AsyncMock(return_value=_response(org_id, **kwargs)),
    )


def _rate_limits_url(org_id: UUID) -> str:
    return f"/v1/organizations/{org_id}/rate-limits"


def test_get_rate_limits_defaults() -> None:
    org_id = uuid4()
    with (
        managed_org_client(ManagedClientOpts(org_id=org_id)) as (client, _, _),
        _mock_service("get_rate_limits", org_id),
    ):
        resp = client.get(_rate_limits_url(org_id), headers=bearer_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["requests_per_minute"] == 60
    assert body["source"] == "default"
    assert body["current_minute_requests"] == 0


def test_patch_rate_limits_owner_ok() -> None:
    org_id = uuid4()
    pub = RecordingRateLimitConfigPublisher()
    with (
        managed_org_client(ManagedClientOpts(org_id=org_id)) as (client, _, _),
        _mock_service(
            "patch_rate_limits", org_id, rpm=120, source="override", current=3
        ) as patched,
    ):
        client.app.state.api.rate_limit_config_publisher = pub
        resp = client.patch(
            _rate_limits_url(org_id),
            headers=bearer_headers(),
            json={"requests_per_minute": 120},
        )
    assert resp.status_code == 200
    assert resp.json()["requests_per_minute"] == 120
    assert patched.await_count == 1


def test_member_and_viewer_patch_denied() -> None:
    org_id = uuid4()
    for role in ("member", "viewer"):
        with managed_org_client(
            ManagedClientOpts(
                org_id=org_id,
                role=role,
                result=ValidateResult(
                    org_id=org_id,
                    permissions=MEMORY_READ,
                    user_id=str(uuid4()),
                ),
            )
        ) as (client, _, _):
            resp = client.patch(
                _rate_limits_url(org_id),
                headers=bearer_headers(),
                json={"requests_per_minute": 10},
            )
        assert resp.status_code == 403, role
        assert resp.json()["error"]["code"] == INSUFFICIENT_PERMISSIONS


def test_admin_patch_allowed() -> None:
    org_id = uuid4()
    with (
        managed_org_client(ManagedClientOpts(org_id=org_id, role="admin")) as (
            client,
            _,
            _,
        ),
        _mock_service("patch_rate_limits", org_id, rpm=90, source="override"),
    ):
        resp = client.patch(
            _rate_limits_url(org_id),
            headers=bearer_headers(),
            json={"requests_per_minute": 90},
        )
    assert resp.status_code == 200


def test_TestAPI_ISO_RATELIMIT_get_foreign_org_404() -> None:
    _assert_foreign_org_404("GET")


def test_TestAPI_ISO_RATELIMIT_patch_foreign_org_404() -> None:
    _assert_foreign_org_404("PATCH")


def _assert_foreign_org_404(method: str) -> None:
    token_org = uuid4()
    path = _rate_limits_url(uuid4())
    with managed_org_client(
        ManagedClientOpts(org_id=token_org, result=owner_result(org_id=token_org))
    ) as (client, _, _):
        call = client.get if method == "GET" else client.patch
        kwargs = {"headers": bearer_headers()}
        if method == "PATCH":
            kwargs["json"] = {"requests_per_minute": 5}
        resp = call(path, **kwargs)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == NOT_FOUND


def test_router_uses_settings_defaults() -> None:
    org_id = uuid4()
    with (
        managed_org_client(ManagedClientOpts(org_id=org_id)) as (client, _, _),
        _mock_service("get_rate_limits", org_id),
    ):
        client.app.state.api.settings = None
        resp = client.get(_rate_limits_url(org_id), headers=bearer_headers())
    assert resp.status_code == 200
