"""Redis-backed idempotency store (mirrors packages/idempotency)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

CURRENT_RECORD_VERSION = 1


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
    return f"idempotency:{token.org_id}:{token.key}"


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
        key = redis_key(token)
        record = IdempotencyRecord(
            fingerprint=fingerprint,
            state=IdempotencyState.COMPLETED,
            status=status,
            body=body,
        )
        await self._client.set(key, record.to_json(), ex=self._ttl)

    async def release(self, token: IdempotencyToken, fingerprint: str) -> None:
        key = redis_key(token)
        raw = await self._client.get(key)
        if raw is None:
            return
        record = IdempotencyRecord.from_json(
            raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        )
        if record.state == IdempotencyState.PENDING and record.fingerprint == fingerprint:
            await self._client.delete(key)


def pending_record(fingerprint: str) -> IdempotencyRecord:
    return IdempotencyRecord(fingerprint=fingerprint, state=IdempotencyState.PENDING)
