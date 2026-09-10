"""Unit tests for provider credential validate-before-store."""

from __future__ import annotations

import asyncio
from typing import Self
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from apierror_py import INVALID_CREDENTIAL

from app.errors import ApiError
from app.services.provider_validate import validate_provider_credential


class _StreamCM:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> bool:
        return False


def _ok_client(status_code: int = 200) -> AsyncMock:
    client = AsyncMock()
    client.stream = MagicMock(return_value=_StreamCM(status_code))
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
    client.stream.assert_called_once()
    args, kwargs = client.stream.call_args
    assert args[0] == "GET"
    assert args[1] == "https://api.openai.com/v1/models"
    assert kwargs["headers"]["Authorization"] == "Bearer sk-test"


@pytest.mark.asyncio
async def test_validate_anthropic_headers() -> None:
    client = _ok_client()
    await validate_provider_credential(
        provider_name="anthropic",
        api_key="sk-ant",
        client=client,
    )
    _, kwargs = client.stream.call_args
    assert kwargs["headers"]["x-api-key"] == "sk-ant"
    assert "anthropic-version" in kwargs["headers"]


@pytest.mark.asyncio
async def test_validate_azure_requires_base_url_and_api_key_header() -> None:
    client = _ok_client()
    with patch(
        "app.services.provider_validate_dest.assert_public_resolved_host",
        new=AsyncMock(),
    ):
        await validate_provider_credential(
            provider_name="azure_openai",
            api_key="az-key",
            base_url="https://myres.openai.azure.com",
            client=client,
        )
    args, kwargs = client.stream.call_args
    assert args[1].startswith("https://myres.openai.azure.com/openai/models?")
    assert kwargs["headers"]["api-key"] == "az-key"


@pytest.mark.asyncio
async def test_validate_azure_rejects_missing_base_url() -> None:
    client = AsyncMock()
    await _expect_invalid(provider_name="azure_openai", api_key="az-key", client=client)
    client.stream.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "status"),
    [
        ({"provider_name": "unknown_provider", "api_key": "sk"}, None),
        (
            {
                "provider_name": "azure_openai",
                "api_key": "az-key",
                "base_url": "https://evil.example.com",
            },
            None,
        ),
        ({"provider_name": "openai", "api_key": "sk", "base_url": "https://10.0.0.1"}, None),
        (
            {
                "provider_name": "vllm_self_hosted",
                "api_key": "local",
                "base_url": "ftp://127.0.0.1:8000/",
            },
            None,
        ),
        ({"provider_name": "openai", "api_key": "sk-bad"}, 401),
        ({"provider_name": "openai", "api_key": "sk-test"}, 302),
    ],
    ids=[
        "unknown_provider",
        "azure_non_azure_host",
        "blocked_literal_ip",
        "malformed_scheme",
        "upstream_4xx",
        "redirect_302",
    ],
)
async def test_validate_rejects_invalid_inputs(kwargs: dict, status: int | None) -> None:
    client: AsyncMock | object = _ok_client(status) if status is not None else AsyncMock()
    await _expect_invalid(client=client, **kwargs)


@pytest.mark.asyncio
async def test_validate_transport_error() -> None:
    client = AsyncMock()
    client.stream = MagicMock(side_effect=httpx.ConnectError("boom"))
    await _expect_invalid(provider_name="openai", api_key="sk-test", client=client)


@pytest.mark.asyncio
async def test_validate_self_hosted_http_loopback() -> None:
    client = _ok_client()
    await validate_provider_credential(
        provider_name="vllm_self_hosted",
        api_key="local",
        base_url="http://127.0.0.1:8000/",
        client=client,
    )
    args, _ = client.stream.call_args
    assert args[1] == "http://127.0.0.1:8000/v1/models"


@pytest.mark.asyncio
async def test_validate_rejects_http_mesh_for_self_hosted() -> None:
    client = AsyncMock()
    await _expect_invalid(
        provider_name="vllm_self_hosted",
        api_key="local",
        base_url="http://llm:8000/",
        client=client,
    )
    client.stream.assert_not_called()


@pytest.mark.asyncio
async def test_validate_rejects_http_non_loopback_for_cloud() -> None:
    client = AsyncMock()
    await _expect_invalid(
        provider_name="openai",
        api_key="sk-test",
        base_url="http://evil.example/v1",
        client=client,
    )
    client.stream.assert_not_called()


@pytest.mark.asyncio
async def test_validate_owns_and_closes_client() -> None:
    fake = _ok_client()
    fake.aclose = AsyncMock()
    with patch("app.services.provider_validate.httpx.AsyncClient", return_value=fake):
        await validate_provider_credential(provider_name="openai", api_key="sk")
    fake.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_validate_rejects_dns_failure_for_custom_host() -> None:
    with patch(
        "app.services.provider_validate_net.resolved_addrs",
        new=AsyncMock(return_value=[]),
    ):
        await _expect_invalid(
            provider_name="openai",
            api_key="sk",
            base_url="https://missing.example",
            client=AsyncMock(),
        )


@pytest.mark.asyncio
async def test_validate_rejects_private_resolved_host() -> None:
    import ipaddress

    with patch(
        "app.services.provider_validate_net.resolved_addrs",
        new=AsyncMock(return_value=[ipaddress.ip_address("10.1.2.3")]),
    ):
        await _expect_invalid(
            provider_name="openai",
            api_key="sk",
            base_url="https://internal.example",
            client=AsyncMock(),
        )


@pytest.mark.asyncio
async def test_validate_deadline_exceeded() -> None:
    async def _hang(*_a, **_k):
        await asyncio.sleep(10)

    with (
        patch("app.services.provider_validate._VALIDATE_DEADLINE", 0.01),
        patch(
            "app.services.provider_validate.assert_probe_destination",
            new=_hang,
        ),
    ):
        await _expect_invalid(provider_name="openai", api_key="sk", client=AsyncMock())


@pytest.mark.asyncio
async def test_validate_self_hosted_https_loopback_allowed() -> None:
    client = _ok_client()
    await validate_provider_credential(
        provider_name="vllm_self_hosted",
        api_key="local",
        base_url="https://127.0.0.1:8000/",
        client=client,
    )
    args, _ = client.stream.call_args
    assert args[1] == "https://127.0.0.1:8000/v1/models"


@pytest.mark.asyncio
async def test_validate_rejects_self_hosted_https_non_loopback() -> None:
    client = AsyncMock()
    await _expect_invalid(
        provider_name="vllm_self_hosted",
        api_key="local",
        base_url="https://llm.internal/",
        client=client,
    )
    client.stream.assert_not_called()
