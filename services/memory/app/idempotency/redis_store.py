"""Redis-backed idempotency store (mirrors packages/idempotency)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

CURRENT_RECORD_VERSION = 1

# Atomic check-and-set: only mutate when record is pending with matching fingerprint.
_CAS_MUTATE_LUA = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local ok, data = pcall(cjson.decode, raw)
if not ok then return 0 end
if data['state'] ~= 'pending' or data['fp'] ~= ARGV[1] then return 0 end
if ARGV[2] == '' then
  return redis.call('DEL', KEYS[1])
end
redis.call('SET', KEYS[1], ARGV[2], 'EX', tonumber(ARGV[3]))
return 1
"""


class IdempotencyState(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"


class ClaimKind(StrEnum):
    MISS = "miss"
    HIT = "hit"
    CONFLICT = "conflict"
    IN_PROGRESS = "in_progress"


@dataclass(frozen=True, slots=True)
class IdempotencyToken:
    org_id: UUID
    key: str


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    fingerprint: str
    state: IdempotencyState
    status: int = 0
    body: bytes = b""

    def to_json(self) -> str:
        payload: dict[str, Any] = {
            "v": CURRENT_RECORD_VERSION,
            "state": self.state.value,
            "fp": self.fingerprint,
        }
        if self.state == IdempotencyState.COMPLETED:
            payload["status"] = self.status
            payload["body"] = self.body.decode("utf-8")
        return json.dumps(payload)

    @classmethod
    def from_json(cls, raw: str) -> IdempotencyRecord:
        data = json.loads(raw)
        if data.get("v") != CURRENT_RECORD_VERSION:
            msg = "unsupported idempotency record version"
            raise ValueError(msg)
        state = IdempotencyState(str(data["state"]))
        body_raw = data.get("body", "")
        body = body_raw.encode("utf-8") if isinstance(body_raw, str) else b""
        return cls(
            fingerprint=str(data["fp"]),
            state=state,
            status=int(data.get("status", 0)),
            body=body,
        )


@dataclass(frozen=True, slots=True)
class ClaimOutcome:
    kind: ClaimKind
    record: IdempotencyRecord | None = None


def redis_key(token: IdempotencyToken) -> str:
    return f"{token.org_id}:idempotency:{token.key}"


class RedisIdempotencyStore:
    def __init__(
        self,
        client: Redis,
        *,
        ttl_seconds: int = 86400,
        pending_ttl_seconds: int = 540,
    ) -> None:
        self._client = client
        self._ttl = ttl_seconds
        self._pending_ttl = pending_ttl_seconds
        self._cas_mutate = client.register_script(_CAS_MUTATE_LUA)

    async def claim(self, token: IdempotencyToken, fingerprint: str) -> ClaimOutcome:
        key = redis_key(token)
        pending = IdempotencyRecord(
            fingerprint=fingerprint, state=IdempotencyState.PENDING
        ).to_json()
        claimed = await self._client.set(key, pending, nx=True, ex=self._pending_ttl)
        if claimed:
            return ClaimOutcome(kind=ClaimKind.MISS, record=pending_record(fingerprint))
        raw = await self._client.get(key)
        if raw is None:
            claimed = await self._client.set(key, pending, nx=True, ex=self._pending_ttl)
            if claimed:
                return ClaimOutcome(kind=ClaimKind.MISS, record=pending_record(fingerprint))
            raw = await self._client.get(key)
        if raw is None:
            return ClaimOutcome(kind=ClaimKind.IN_PROGRESS)
        record = IdempotencyRecord.from_json(
            raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        )
        if record.fingerprint != fingerprint:
            return ClaimOutcome(kind=ClaimKind.CONFLICT, record=record)
        if record.state == IdempotencyState.COMPLETED:
            return ClaimOutcome(kind=ClaimKind.HIT, record=record)
        return ClaimOutcome(kind=ClaimKind.IN_PROGRESS, record=record)

    async def commit(
        self,
        token: IdempotencyToken,
        *,
        fingerprint: str,
        status: int,
        body: bytes,
    ) -> None:
        record = IdempotencyRecord(
            fingerprint=fingerprint,
            state=IdempotencyState.COMPLETED,
            status=status,
            body=body,
        )
        await self._mutate_if_pending(
            token,
            fingerprint,
            completed_json=record.to_json(),
        )

    async def release(self, token: IdempotencyToken, fingerprint: str) -> None:
        await self._mutate_if_pending(token, fingerprint, completed_json=None)

    async def _mutate_if_pending(
        self,
        token: IdempotencyToken,
        fingerprint: str,
        *,
        completed_json: str | None,
    ) -> None:
        key = redis_key(token)
        payload = completed_json or ""
        await self._cas_mutate(
            keys=[key],
            args=[fingerprint, payload, str(self._ttl)],
        )


def pending_record(fingerprint: str) -> IdempotencyRecord:
    return IdempotencyRecord(fingerprint=fingerprint, state=IdempotencyState.PENDING)
