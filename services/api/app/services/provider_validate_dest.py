"""Destination checks for provider credential validate probes."""

from __future__ import annotations

from urllib.parse import urlparse

from app.services.provider_validate_net import (
    assert_public_resolved_host,
    invalid,
    literal_ip,
)

_CLOUD_DEFAULT_HOSTS: dict[str, frozenset[str]] = {
    "openai": frozenset({"api.openai.com"}),
    "anthropic": frozenset({"api.anthropic.com"}),
    "bedrock": frozenset({"api.openai.com"}),
}


async def assert_probe_destination(provider_name: str, url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or parsed.scheme not in {"http", "https"}:
        raise invalid()
    if provider_name == "vllm_self_hosted":
        await _assert_self_hosted_destination(parsed.scheme, host)
        return
    await _assert_cloud_destination(provider_name, parsed.scheme, host)


async def _assert_cloud_destination(provider_name: str, scheme: str, host: str) -> None:
    if scheme != "https":
        raise invalid()
    if provider_name == "azure_openai":
        await _assert_azure_host(host)
        return
    if host in _CLOUD_DEFAULT_HOSTS.get(provider_name, frozenset()):
        return
    await assert_public_resolved_host(host)


async def _assert_azure_host(host: str) -> None:
    if not (host.endswith(".openai.azure.com") or host == "openai.azure.com"):
        raise invalid()
    await assert_public_resolved_host(host)


async def _assert_self_hosted_destination(scheme: str, host: str) -> None:
    if scheme not in {"http", "https"}:
        raise invalid()
    # Both plaintext and TLS self-hosted probes are limited to literal loopback.
    literal = literal_ip(host)
    if literal is None or not literal.is_loopback:
        raise invalid()
