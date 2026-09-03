"""Shared OpenAI-compatible chat-completions HTTP client for extraction."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

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
    return _parse_completion_body(
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


def _parse_completion_body(
    body: Any, *, fallback_model: str, started: float
) -> ExtractionCall:
    raw = _normalized_content_json(_message_content(body))
    input_tokens, output_tokens = _usage_tokens(body)
    model = _response_model(body, fallback_model)
    return ExtractionCall(
        raw_json=raw,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=int((time.monotonic() - started) * 1000),
    )


def _response_model(body: Any, fallback_model: str) -> str:
    if isinstance(body, dict):
        return str(body.get("model") or fallback_model)
    return fallback_model


def _normalized_content_json(content: str) -> str:
    raw = content.strip()
    if raw.startswith("```"):
        raw = _strip_fence(raw)
    try:
        json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExtractionProviderError("extraction provider content is not JSON") from exc
    return raw


def _require_mapping(value: Any, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExtractionProviderError(message)
    return value


def _message_content(body: Any) -> str:
    payload = _require_mapping(body, "extraction provider returned non-object JSON")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ExtractionProviderError("extraction provider response missing choices")
    first = _require_mapping(choices[0], "extraction provider choice is not an object")
    message = _require_mapping(first.get("message"), "extraction provider message missing")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ExtractionProviderError("extraction provider content empty")
    return content


def _usage_tokens(body: Any) -> tuple[int, int]:
    usage = body.get("usage") if isinstance(body, dict) else None
    if not isinstance(usage, dict):
        return 0, 0
    return int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)


def _strip_fence(raw: str) -> str:
    lines = raw.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
