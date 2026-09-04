"""Directive Redis cache lookup (milestone 3.5.C.2).

Reads the same envelope written by packages/directive (Go):

  key: ``{org_id}:directive:{agent_id}``
  value: ``{"v":1,"content":"...","injection_mode":"...","version_id":"..."}``

No Postgres fallback — proxy owns cache fill; miss/error fail-opens empty.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

_ENVELOPE_VERSION = 1
_DEFAULT_INJECTION_MODE = "system_first"
_KNOWN_INJECTION_MODES = frozenset(
    {"system_first", "system_append", "user_prepend"}
)


@dataclass(frozen=True, slots=True)
class DirectivePayload:
    content: str
    injection_mode: str
    version_id: str | None


class DirectiveLookup(Protocol):
    async def lookup(self, org_id: UUID, agent_id: UUID) -> DirectivePayload: ...


class EmptyDirectiveLookup:
    """Test / disabled stub — always returns empty content."""

    async def lookup(self, org_id: UUID, agent_id: UUID) -> DirectivePayload:
        # Yield once so the Protocol stay awaitable without a fake async helper.
        await asyncio.sleep(0)
        _ = f"{org_id}:{agent_id}"
        return _empty_payload()


class DirectiveLookupError(Exception):
    """Redis / envelope failure (mapped to branch error by orchestrator)."""


class RedisDirectiveLookup:
    """GET ``{org_id}:directive:{agent_id}`` and parse the Go cache envelope."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def lookup(self, org_id: UUID, agent_id: UUID) -> DirectivePayload:
        key = f"{org_id}:directive:{agent_id}"
        try:
            raw = await self._redis.get(key)
        except (OSError, RedisError) as exc:
            raise DirectiveLookupError("directive redis get failed") from exc
        if raw is None:
            return _empty_payload()
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        except UnicodeDecodeError as exc:
            raise DirectiveLookupError("directive envelope is not valid UTF-8") from exc
        return _parse_envelope(text)


def _empty_payload() -> DirectivePayload:
    return DirectivePayload(
        content="",
        injection_mode=_DEFAULT_INJECTION_MODE,
        version_id=None,
    )


def _parse_envelope(raw: str) -> DirectivePayload:
    data = _load_envelope_object(raw)
    _require_envelope_version(data)
    return _payload_from_envelope(data)


def _load_envelope_object(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DirectiveLookupError("directive envelope is not JSON") from exc
    if not isinstance(data, dict):
        raise DirectiveLookupError("directive envelope is not an object")
    return data


def _require_envelope_version(data: dict[str, Any]) -> None:
    version = data.get("v")
    if version != _ENVELOPE_VERSION:
        raise DirectiveLookupError(f"unsupported directive envelope version {version!r}")


def _payload_from_envelope(data: dict[str, Any]) -> DirectivePayload:
    content = _require_string_field(data, "content", allow_empty=True)
    mode_raw = data.get("injection_mode", "")
    if mode_raw is None:
        mode_raw = ""
    if not isinstance(mode_raw, str):
        raise DirectiveLookupError("directive injection_mode must be a string")
    mode = _normalize_injection_mode(mode_raw)
    version_id_str = _optional_version_id(data.get("version_id"))
    return DirectivePayload(content=content, injection_mode=mode, version_id=version_id_str)


def _require_string_field(data: dict[str, Any], key: str, *, allow_empty: bool) -> str:
    value = data.get(key, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise DirectiveLookupError(f"directive {key} must be a string")
    if not allow_empty and not value:
        raise DirectiveLookupError(f"directive {key} must not be empty")
    return value


def _normalize_injection_mode(raw: str) -> str:
    mode = raw.strip() or _DEFAULT_INJECTION_MODE
    if mode not in _KNOWN_INJECTION_MODES:
        return _DEFAULT_INJECTION_MODE
    return mode


def _optional_version_id(value: object) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise DirectiveLookupError("directive version_id must be a string")
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise DirectiveLookupError("directive version_id must be a UUID") from exc
