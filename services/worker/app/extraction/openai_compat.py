"""Shared OpenAI-compatible chat-completions HTTP client for extraction."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.extraction.openai_compat_parse import parse_completion_body
from app.extraction.provider import (
    ExtractionCall,
    ExtractionProviderError,
    ExtractionTransportError,
)

_RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})


@dataclass(frozen=True, slots=True)
class CompatEndpoint:
    """Connection settings for an OpenAI-compatible chat-completions server."""

    base_url: str
    model: str
    api_key: str | None
    timeout_seconds: float


def post_chat_completion(
    client: httpx.Client,
    endpoint: CompatEndpoint,
    prompts: tuple[str, str],
) -> ExtractionCall:
    """POST /chat/completions and map the response to ExtractionCall."""
    system_prompt, user_content = prompts
    started = time.monotonic()
    response = _post_completion(client, endpoint, system_prompt, user_content)
    _raise_for_http_status(response)
    return parse_completion_body(
        _response_json(response),
        fallback_model=endpoint.model,
        started=started,
    )


def _response_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise ExtractionProviderError("extraction provider returned invalid JSON") from exc


def _post_completion(
    client: httpx.Client,
    endpoint: CompatEndpoint,
    system_prompt: str,
    user_content: str,
) -> httpx.Response:
    url = endpoint.base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if endpoint.api_key:
        headers["Authorization"] = f"Bearer {endpoint.api_key}"
    payload = {
        "model": endpoint.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.0,
    }
    try:
        return client.post(
            url, headers=headers, json=payload, timeout=endpoint.timeout_seconds
        )
    except httpx.TimeoutException as exc:
        raise ExtractionTransportError("extraction provider timeout") from exc
    except httpx.TransportError as exc:
        raise ExtractionTransportError("extraction provider transport error") from exc


def _raise_for_http_status(response: httpx.Response) -> None:
    if response.status_code in _RETRYABLE_STATUS:
        raise ExtractionTransportError(
            f"extraction provider HTTP {response.status_code}"
        )
    if response.status_code >= 400:
        raise ExtractionProviderError(f"extraction provider HTTP {response.status_code}")
