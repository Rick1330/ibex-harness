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
    started = time.monotonic()
    try:
        response = client.post(
            url, headers=headers, json=payload, timeout=endpoint.timeout_seconds
        )
    except httpx.TimeoutException as exc:
        raise ExtractionTransportError("extraction provider timeout") from exc
    except httpx.TransportError as exc:
        raise ExtractionTransportError("extraction provider transport error") from exc
    if response.status_code in _RETRYABLE_STATUS:
        raise ExtractionTransportError(
            f"extraction provider HTTP {response.status_code}"
        )
    if response.status_code >= 400:
        raise ExtractionProviderError(f"extraction provider HTTP {response.status_code}")
    return _parse_completion_body(
        response.json(), fallback_model=endpoint.model, started=started
    )


def _parse_completion_body(
    body: Any, *, fallback_model: str, started: float
) -> ExtractionCall:
    if not isinstance(body, dict):
        raise ExtractionProviderError("extraction provider returned non-object JSON")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ExtractionProviderError("extraction provider response missing choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ExtractionProviderError("extraction provider choice is not an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ExtractionProviderError("extraction provider message missing")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ExtractionProviderError("extraction provider content empty")
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    input_tokens = int(usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or 0)
    model = str(body.get("model") or fallback_model)
    latency_ms = int((time.monotonic() - started) * 1000)
    raw = content.strip()
    if raw.startswith("```"):
        raw = _strip_fence(raw)
    try:
        json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExtractionProviderError("extraction provider content is not JSON") from exc
    return ExtractionCall(
        raw_json=raw,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
    )


def _strip_fence(raw: str) -> str:
    lines = raw.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
