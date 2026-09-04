"""Directive Redis cache lookup (milestone 3.5.C.2).

Reads the same envelope written by packages/directive (Go):

  key: ``{org_id}:directive:{agent_id}``
  value: ``{"v":1,"content":"...","injection_mode":"...","version_id":"..."}``

No Postgres fallback — proxy owns cache fill; miss/error fail-opens empty.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

_ENVELOPE_VERSION = 1
_DEFAULT_INJECTION_MODE = "system_first"


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
        return DirectivePayload(content="", injection_mode=_DEFAULT_INJECTION_MODE, version_id=None)


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
            return DirectivePayload(
                content="",
                injection_mode=_DEFAULT_INJECTION_MODE,
                version_id=None,
            )
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return _parse_envelope(raw)


def _parse_envelope(raw: str) -> DirectivePayload:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DirectiveLookupError("directive envelope is not JSON") from exc
    if not isinstance(data, dict):
        raise DirectiveLookupError("directive envelope is not an object")
    version = data.get("v")
    if version != _ENVELOPE_VERSION:
        raise DirectiveLookupError(f"unsupported directive envelope version {version!r}")
    content = str(data.get("content") or "")
    mode = str(data.get("injection_mode") or "") or _DEFAULT_INJECTION_MODE
    version_id = data.get("version_id")
    version_id_str = str(version_id) if version_id else None
    return DirectivePayload(content=content, injection_mode=mode, version_id=version_id_str)
