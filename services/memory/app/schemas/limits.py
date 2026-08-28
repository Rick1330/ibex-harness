"""Shared validation limits for memory write schemas."""

from __future__ import annotations

import json
from typing import Any

MAX_IDEMPOTENCY_KEY_LENGTH = 256
MAX_BEARER_TOKEN_BYTES = 8192
MAX_TAGS = 20
MAX_TAG_LENGTH = 64
MAX_METADATA_KEYS = 32
MAX_METADATA_DEPTH = 4
MAX_METADATA_BYTES = 8192


def validate_tags(tags: list[str]) -> list[str]:
    if len(tags) > MAX_TAGS:
        msg = f"at most {MAX_TAGS} tags allowed"
        raise ValueError(msg)
    for tag in tags:
        if not tag.strip():
            raise ValueError("tags must not be empty")
        if len(tag) > MAX_TAG_LENGTH:
            msg = f"each tag must be at most {MAX_TAG_LENGTH} characters"
            raise ValueError(msg)
    return tags


def validate_memory_metadata(metadata: dict[str, Any] | None) -> None:
    if metadata is None:
        return
    if len(metadata) > MAX_METADATA_KEYS:
        msg = f"metadata may have at most {MAX_METADATA_KEYS} keys"
        raise ValueError(msg)
    _validate_metadata_depth(metadata, depth=1)
    encoded = json.dumps(metadata, separators=(",", ":"), sort_keys=True)
    if len(encoded.encode("utf-8")) > MAX_METADATA_BYTES:
        msg = f"metadata serialized size must be at most {MAX_METADATA_BYTES} bytes"
        raise ValueError(msg)


def _depth_exceeded(depth: int) -> bool:
    return depth > MAX_METADATA_DEPTH


def _validate_metadata_depth(value: Any, *, depth: int) -> None:
    if not isinstance(value, (dict, list)):
        return
    if _depth_exceeded(depth):
        msg = f"metadata nesting must be at most {MAX_METADATA_DEPTH} levels deep"
        raise ValueError(msg)
    children = value.values() if isinstance(value, dict) else value
    for nested in children:
        _validate_metadata_depth(nested, depth=depth + 1)
