"""Unit tests for provider credential validate-before-store."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from apierror_py import INVALID_CREDENTIAL

from app.errors import ApiError
from app.services.provider_validate import validate_provider_credential


def _ok_client(status_code: int = 200) -> AsyncMock:
    client = AsyncMock()
    client.get = AsyncMock(return_value=MagicMock(status_code=status_code))
    return client


async def _expect_invalid(**kwargs) -> None:
    with pytest.raises(ApiError) as exc:
        await validate_provider_credential(**kwargs)
    assert exc.value.code == INVALID_CREDENTIAL


@pytest.mark.asyncio
async def test_validate_openai_success() -> None:
    client = _ok_client()
    await validate_provider_credential(
        provider_name="openai",
        api_key="sk-test",
        client=client,
    )
    client.get.assert_awaited_once()
    args, kwargs = client.get.await_args
    assert args[0] == "https://api.openai.com/v1/models"
    assert kwargs["headers"]["Authorization"] == "Bearer sk-test"


@pytest.mark.asyncio
async def test_validate_anthropic_headers() -> None:
    client = _ok_client()
    await validate_provider_credential(
        provider_name="anthropic",
        api_key="sk-ant",
        client=client,
    )
    _, kwargs = client.get.await_args
    assert kwargs["headers"]["x-api-key"] == "sk-ant"
    assert "anthropic-version" in kwargs["headers"]


@pytest.mark.asyncio
async def test_validate_azure_requires_base_url_and_api_key_header() -> None:
    client = _ok_client()
    with (
        patch("app.services.provider_validate._resolved_addrs", return_value=[]),
        patch("app.services.provider_validate._assert_public_resolved_host"),
    ):
        await validate_provider_credential(
            provider_name="azure_openai",
            api_key="az-key",
            base_url="https://myres.openai.azure.com",
            client=client,
        )
    args, kwargs = client.get.await_args
    assert args[0].startswith("https://myres.openai.azure.com/openai/models?")
    assert kwargs["headers"]["api-key"] == "az-key"


@pytest.mark.asyncio
async def test_validate_azure_rejects_missing_base_url() -> None:
    client = AsyncMock()
    await _expect_invalid(provider_name="azure_openai", api_key="az-key", client=client)
    client.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_validate_rejects_upstream_4xx() -> None:
    await _expect_invalid(
        provider_name="openai",
        api_key="sk-bad",
        client=_ok_client(401),
    )


@pytest.mark.asyncio
async def test_validate_rejects_redirect_302() -> None:
    await _expect_invalid(
        provider_name="openai",
        api_key="sk-test",
        client=_ok_client(302),
    )


@pytest.mark.asyncio
async def test_validate_transport_error() -> None:
    client = AsyncMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    await _expect_invalid(provider_name="openai", api_key="sk-test", client=client)


@pytest.mark.asyncio
async def test_validate_custom_base_url_self_hosted_mesh() -> None:
    client = _ok_client()
    await validate_provider_credential(
        provider_name="vllm_self_hosted",
        api_key="local",
        base_url="http://llm:8000/",
        client=client,
    )
    args, _ = client.get.await_args
    assert args[0] == "http://llm:8000/v1/models"


@pytest.mark.asyncio
async def test_validate_rejects_http_non_loopback_for_cloud() -> None:
    client = AsyncMock()
    await _expect_invalid(
        provider_name="openai",
        api_key="sk-test",
        base_url="http://evil.example/v1",
        client=client,
    )
    client.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_validate_owns_and_closes_client() -> None:
    fake = _ok_client()
    fake.aclose = AsyncMock()
    with patch("app.services.provider_validate.httpx.AsyncClient", return_value=fake):
        await validate_provider_credential(provider_name="openai", api_key="sk")
    fake.aclose.assert_awaited_once()
