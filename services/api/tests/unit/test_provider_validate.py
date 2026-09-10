"""Unit tests for provider credential validate-before-store."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from apierror_py import INVALID_CREDENTIAL

from app.errors import ApiError
from app.services.provider_validate import validate_provider_credential


@pytest.mark.asyncio
async def test_validate_openai_success() -> None:
    resp = MagicMock(status_code=200)
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
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
    resp = MagicMock(status_code=200)
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    await validate_provider_credential(
        provider_name="anthropic",
        api_key="sk-ant",
        client=client,
    )
    _, kwargs = client.get.await_args
    assert kwargs["headers"]["x-api-key"] == "sk-ant"
    assert "anthropic-version" in kwargs["headers"]


@pytest.mark.asyncio
async def test_validate_rejects_upstream_4xx() -> None:
    resp = MagicMock(status_code=401)
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    with pytest.raises(ApiError) as exc:
        await validate_provider_credential(
            provider_name="openai",
            api_key="sk-bad",
            client=client,
        )
    assert exc.value.code == INVALID_CREDENTIAL


@pytest.mark.asyncio
async def test_validate_transport_error() -> None:
    client = AsyncMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(ApiError) as exc:
        await validate_provider_credential(
            provider_name="openai",
            api_key="sk-test",
            client=client,
        )
    assert exc.value.code == INVALID_CREDENTIAL


@pytest.mark.asyncio
async def test_validate_custom_base_url() -> None:
    resp = MagicMock(status_code=200)
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    await validate_provider_credential(
        provider_name="vllm_self_hosted",
        api_key="local",
        base_url="http://llm:8000/",
        client=client,
    )
    args, _ = client.get.await_args
    assert args[0] == "http://llm:8000/v1/models"


@pytest.mark.asyncio
async def test_validate_owns_and_closes_client() -> None:
    resp = MagicMock(status_code=200)
    fake = AsyncMock()
    fake.get = AsyncMock(return_value=resp)
    fake.aclose = AsyncMock()
    with patch("app.services.provider_validate.httpx.AsyncClient", return_value=fake):
        await validate_provider_credential(provider_name="openai", api_key="sk")
    fake.aclose.assert_awaited_once()
