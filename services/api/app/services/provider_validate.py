"""Validate provider API keys against upstream before Auth store."""

from __future__ import annotations

import asyncio
import logging
from typing import Final

import httpx
from apierror_py import INVALID_CREDENTIAL

from app.errors import ApiError
from app.services.provider_validate_dest import assert_probe_destination
from app.services.provider_validate_net import ProbeDial, url_for_dial

logger = logging.getLogger(__name__)

_VALIDATE_TIMEOUT = httpx.Timeout(5.0, connect=5.0)
_VALIDATE_DEADLINE = 5.0
_AZURE_API_VERSION = "2024-02-01"
_DEFAULT_BASES: Final[dict[str, str]] = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "bedrock": "https://api.openai.com",
    "vllm_self_hosted": "http://127.0.0.1:8000",
}
_INVALID_MSG = "Provider key validation failed"


def _invalid() -> ApiError:
    return ApiError(code=INVALID_CREDENTIAL, message=_INVALID_MSG)


async def validate_provider_credential(
    *,
    provider_name: str,
    api_key: str,
    base_url: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Probe upstream models endpoint; raise INVALID_CREDENTIAL on failure."""
    try:
        async with asyncio.timeout(_VALIDATE_DEADLINE):
            url = _models_url(provider_name, base_url)
            dial = await assert_probe_destination(provider_name, url)
            headers = _auth_headers(provider_name, api_key)
            status = await _probe_models(url, headers, client, dial)
    except TimeoutError:
        logger.info("provider key probe deadline exceeded")
        raise _invalid() from None
    if status < 200 or status >= 300:
        logger.info("provider key probe rejected provider=%s status=%s", provider_name, status)
        raise _invalid()


def _models_url(provider_name: str, base_url: str | None) -> str:
    if provider_name == "azure_openai":
        base = (base_url or "").rstrip("/")
        if not base:
            raise _invalid()
        return f"{base}/openai/models?api-version={_AZURE_API_VERSION}"
    base = (base_url or _DEFAULT_BASES.get(provider_name, "")).rstrip("/")
    if not base:
        raise _invalid()
    return f"{base}/v1/models"


async def _probe_models(
    url: str,
    headers: dict[str, str],
    client: httpx.AsyncClient | None,
    dial: ProbeDial,
) -> int:
    owns_client = client is None
    http = client or httpx.AsyncClient(
        timeout=_VALIDATE_TIMEOUT,
        follow_redirects=False,
    )
    req_url = url_for_dial(url, dial)
    req_headers = dict(headers)
    extensions: dict[str, str] = {}
    if dial.connect_ip is not None:
        req_headers["Host"] = dial.server_name
        if url.startswith("https://"):
            extensions["sni_hostname"] = dial.server_name
    try:
        async with http.stream(
            "GET",
            req_url,
            headers=req_headers,
            extensions=extensions or None,
        ) as resp:
            return resp.status_code
    except httpx.HTTPError:
        logger.info("provider key probe transport failure")
        raise _invalid() from None
    finally:
        if owns_client:
            await http.aclose()


def _auth_headers(provider_name: str, api_key: str) -> dict[str, str]:
    if provider_name == "anthropic":
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    if provider_name == "azure_openai":
        return {"api-key": api_key}
    return {"Authorization": f"Bearer {api_key}"}
