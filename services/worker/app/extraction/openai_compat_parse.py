"""Parse OpenAI-compatible chat-completion JSON into ExtractionCall fields."""

from __future__ import annotations

import json
import time
from typing import Any

from app.extraction.provider import ExtractionCall, ExtractionProviderError


def parse_completion_body(
    body: Any, *, fallback_model: str, started: float
) -> ExtractionCall:
    raw = normalized_content_json(message_content(body))
    input_tokens, output_tokens = usage_tokens(body)
    return ExtractionCall(
        raw_json=raw,
        model=response_model(body, fallback_model),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=int((time.monotonic() - started) * 1000),
    )


def response_model(body: Any, fallback_model: str) -> str:
    if isinstance(body, dict):
        return str(body.get("model") or fallback_model)
    return fallback_model


def normalized_content_json(content: str) -> str:
    raw = content.strip()
    if raw.startswith("```"):
        raw = _strip_fence(raw)
    try:
        json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExtractionProviderError("extraction provider content is not JSON") from exc
    return raw


def require_mapping(value: Any, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExtractionProviderError(message)
    return value


def first_choice(payload: dict[str, Any]) -> dict[str, Any]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ExtractionProviderError("extraction provider response missing choices")
    return require_mapping(choices[0], "extraction provider choice is not an object")


def content_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ExtractionProviderError("extraction provider content empty")
    return content


def message_content(body: Any) -> str:
    payload = require_mapping(body, "extraction provider returned non-object JSON")
    choice = first_choice(payload)
    message = require_mapping(choice.get("message"), "extraction provider message missing")
    return content_text(message)


def usage_tokens(body: Any) -> tuple[int, int]:
    usage = body.get("usage") if isinstance(body, dict) else None
    if not isinstance(usage, dict):
        return 0, 0
    return (
        _nonneg_int_token(usage.get("prompt_tokens"), "prompt_tokens"),
        _nonneg_int_token(usage.get("completion_tokens"), "completion_tokens"),
    )


def _nonneg_int_token(value: Any, field: str) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExtractionProviderError(f"extraction provider {field} must be an integer")
    if value < 0:
        raise ExtractionProviderError(f"extraction provider {field} must be non-negative")
    return value


def _strip_fence(raw: str) -> str:
    lines = raw.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
