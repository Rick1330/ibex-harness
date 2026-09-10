"""Unit tests for provider credential service mapping."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from apierror_py import AUTH_UNAVAILABLE, INSUFFICIENT_PERMISSIONS, INVALID_TOKEN, NOT_FOUND
from authclient.codec import ProviderCredentialMetadataWire
from authclient.errors import (
    AuthFailedError,
    AuthUnavailableError,
    InsufficientPermissionsError,
    ProviderCredentialNotFoundError,
)
from authclient.provider_credentials import FakeProviderCredentialManager

from app.auth.client import ValidateResult
from app.errors import ApiError
from app.schemas.providers import ProviderCredentialUpsertRequest
from app.services.providers import (
    ProviderCredentialAccess,
    delete_provider_credential,
    list_provider_credentials,
    upsert_provider_credential,
)


def _access(mgr: FakeProviderCredentialManager) -> ProviderCredentialAccess:
    return ProviderCredentialAccess(
        token=ValidateResult(org_id=uuid4(), permissions=0, user_id=str(uuid4())),
        access_token="tok",
        manager=mgr,
    )


@pytest.mark.asyncio
async def test_list_and_delete_happy_path() -> None:
    org = uuid4()
    mgr = FakeProviderCredentialManager()
    mgr.seed(
        str(org),
        ProviderCredentialMetadataWire(
            provider_name="openai",
            status="active",
            key_hint="zzzz",
            encryption_key_id="v1",
            last_validated_at=datetime.now(tz=UTC),
        ),
    )
    access = _access(mgr)
    listed = await list_provider_credentials(access, org)
    assert len(listed.credentials) == 1
    await delete_provider_credential(access, org, "openai")
    assert (str(org), "openai") in mgr.deleted


@pytest.mark.asyncio
async def test_upsert_maps_auth_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _ok(**_kwargs):
        return None

    monkeypatch.setattr(
        "app.services.providers.provider_validate.validate_provider_credential",
        _ok,
    )
    mgr = FakeProviderCredentialManager()
    mgr.create_error = InsufficientPermissionsError()
    access = _access(mgr)
    body = ProviderCredentialUpsertRequest(provider_name="openai", api_key="sk-test")
    with pytest.raises(ApiError) as exc:
        await upsert_provider_credential(access, uuid4(), body)
    assert exc.value.code == INSUFFICIENT_PERMISSIONS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("err", "code"),
    [
        (ProviderCredentialNotFoundError(), NOT_FOUND),
        (AuthFailedError("bad"), INVALID_TOKEN),
        (AuthUnavailableError(), AUTH_UNAVAILABLE),
    ],
)
async def test_delete_maps_errors(err: BaseException, code: str) -> None:
    mgr = FakeProviderCredentialManager()
    mgr.delete_error = err
    access = _access(mgr)
    with pytest.raises(ApiError) as exc:
        await delete_provider_credential(access, uuid4(), "openai")
    assert exc.value.code == code
