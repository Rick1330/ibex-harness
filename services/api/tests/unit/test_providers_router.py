"""Unit tests for provider credential routes."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from authclient.codec import ProviderCredentialMetadataWire
from authclient.permissions import MEMORY_READ
from authclient.provider_credentials import FakeProviderCredentialManager

from app.auth.client import ValidateResult
from tests.unit.org_user_test_support import (
    ManagedClientOpts,
    bearer_headers,
    managed_org_client,
    owner_result,
)


def test_list_and_upsert_provider_credentials() -> None:
    org_id = uuid4()
    mgr = FakeProviderCredentialManager()
    mgr.seed(
        str(org_id),
        ProviderCredentialMetadataWire(
            provider_name="openai",
            status="active",
            key_hint="abcd",
            encryption_key_id="v1",
            last_validated_at=datetime.now(tz=UTC),
        ),
        api_key="sk-seedabcd",
    )
    with (
        managed_org_client(
            ManagedClientOpts(org_id=org_id, provider_credential_manager=mgr)
        ) as (client, _, _),
        patch(
            "app.services.provider_validate.validate_provider_credential",
            new=AsyncMock(),
        ),
    ):
        listed = client.get(
            f"/v1/organizations/{org_id}/providers", headers=bearer_headers()
        )
        assert listed.status_code == 200
        assert listed.json()["credentials"][0]["provider_name"] == "openai"
        assert "api_key" not in listed.json()["credentials"][0]

        created = client.post(
            f"/v1/organizations/{org_id}/providers",
            headers=bearer_headers(),
            json={"provider_name": "anthropic", "api_key": "sk-ant-testkey"},
        )
        assert created.status_code == 201
        body = created.json()
        assert body["provider_name"] == "anthropic"
        assert body["key_hint"] == "tkey"
        assert "api_key" not in body


def test_upsert_invalid_credential_returns_422() -> None:
    org_id = uuid4()
    from apierror_py import INVALID_CREDENTIAL

    from app.errors import ApiError

    async def _fail(**_kwargs):
        raise ApiError(code=INVALID_CREDENTIAL, message="Provider credential validation failed")

    with (
        managed_org_client(
            ManagedClientOpts(
                org_id=org_id,
                provider_credential_manager=FakeProviderCredentialManager(),
            )
        ) as (client, _, _),
        patch(
            "app.services.provider_validate.validate_provider_credential",
            new=_fail,
        ),
    ):
        resp = client.post(
            f"/v1/organizations/{org_id}/providers",
            headers=bearer_headers(),
            json={"provider_name": "openai", "api_key": "sk-bad"},
        )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_CREDENTIAL"


def test_cross_tenant_providers_return_404() -> None:
    token_org = uuid4()
    other_org = uuid4()
    with managed_org_client(
        ManagedClientOpts(
            org_id=token_org,
            result=owner_result(org_id=token_org),
            provider_credential_manager=FakeProviderCredentialManager(),
        )
    ) as (client, _, _):
        resp = client.get(
            f"/v1/organizations/{other_org}/providers", headers=bearer_headers()
        )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_member_without_org_settings_denied() -> None:
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
            provider_credential_manager=FakeProviderCredentialManager(),
        )
    ) as (client, _, _):
        resp = client.get(
            f"/v1/organizations/{org_id}/providers", headers=bearer_headers()
        )
    assert resp.status_code == 403


def test_delete_provider_credential() -> None:
    org_id = uuid4()
    mgr = FakeProviderCredentialManager()
    mgr.seed(
        str(org_id),
        ProviderCredentialMetadataWire(
            provider_name="openai",
            status="active",
            key_hint="zzzz",
            encryption_key_id="v1",
        ),
    )
    with managed_org_client(
        ManagedClientOpts(org_id=org_id, provider_credential_manager=mgr)
    ) as (client, _, _):
        resp = client.delete(
            f"/v1/organizations/{org_id}/providers/openai",
            headers=bearer_headers(),
        )
    assert resp.status_code == 204
    assert ("openai" in {name for _, name in mgr.deleted}) or (
        (str(org_id), "openai") in mgr.deleted
    )
