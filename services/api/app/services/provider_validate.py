"""Validate provider API keys against upstream before Auth store."""

from __future__ import annotations

import logging
from typing import Final

import httpx
from apierror_py import INVALID_CREDENTIAL

from app.errors import ApiError

logger = logging.getLogger(__name__)

_VALIDATE_TIMEOUT = httpx.Timeout(5.0, connect=5.0)
_DEFAULT_BASES: Final[dict[str, str]] = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "azure_openai": "https://api.openai.com",
    "bedrock": "https://api.openai.com",
    "vllm_self_hosted": "http://127.0.0.1:8000",
}


async def validate_provider_credential(
    *,
    provider_name: str,
    api_key: str,
    base_url: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Probe upstream models endpoint; raise INVALID_CREDENTIAL on failure."""
    base = (base_url or _DEFAULT_BASES.get(provider_name, "")).rstrip("/")
    if not base:
        raise ApiError(
            code=INVALID_CREDENTIAL,
            message="Provider credential validation failed",
        )
    url = f"{base}/v1/models"
    headers = _auth_headers(provider_name, api_key)
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=_VALIDATE_TIMEOUT)
    try:
        resp = await http.get(url, headers=headers)
    except httpx.HTTPError:
        logger.info(
            "provider credential validation transport failure provider=%s",
            provider_name,
        )
        raise ApiError(
            code=INVALID_CREDENTIAL,
            message="Provider credential validation failed",
        ) from None
    finally:
        if owns_client:
            await http.aclose()
    if resp.status_code >= 400:
        logger.info(
            "provider credential validation rejected provider=%s status=%s",
            provider_name,
            resp.status_code,
        )
        raise ApiError(
            code=INVALID_CREDENTIAL,
            message="Provider credential validation failed",
        )


def _auth_headers(provider_name: str, api_key: str) -> dict[str, str]:
    if provider_name == "anthropic":
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    return {"Authorization": f"Bearer {api_key}"}
