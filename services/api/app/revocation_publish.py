"""Publish org_suspend events on the ADR-0029 revocation channel."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from datetime import UTC, datetime
from typing import Protocol

logger = logging.getLogger(__name__)

REVOCATION_CHANNEL = "ibex:token:revocations"
_PUBLISH_MAX_ATTEMPTS = 3
_PUBLISH_BACKOFF_BASE_SECONDS = 0.05
_PUBLISH_BACKOFF_MAX_SECONDS = 1.0


class OrgSuspendPublisher(Protocol):
    async def publish_org_suspend(self, org_id: str) -> None: ...


class NoopOrgSuspendPublisher:
    async def publish_org_suspend(self, org_id: str) -> None:
        del org_id
        await asyncio.sleep(0)


class RecordingOrgSuspendPublisher:
    """Test double that records published org IDs and payloads."""

    def __init__(self) -> None:
        self.org_ids: list[str] = []
        self.payloads: list[dict[str, object]] = []

    async def publish_org_suspend(self, org_id: str) -> None:
        await asyncio.sleep(0)
        payload = org_suspend_payload(org_id)
        self.org_ids.append(org_id)
        self.payloads.append(payload)


def _publish_backoff_seconds(attempt: int) -> float:
    cap = min(_PUBLISH_BACKOFF_BASE_SECONDS * (2**attempt), _PUBLISH_BACKOFF_MAX_SECONDS)
    return (secrets.randbelow(1_000_000) / 1_000_000) * cap


class RedisOrgSuspendPublisher:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            from redis.asyncio import Redis

            self._client = Redis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def publish_org_suspend(self, org_id: str) -> None:
        payload = org_suspend_payload(org_id)
        last_exc: Exception | None = None
        for attempt in range(_PUBLISH_MAX_ATTEMPTS):
            try:
                client = self._get_client()
                await client.publish(
                    REVOCATION_CHANNEL, json.dumps(payload, separators=(",", ":"))
                )
                return
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "org_suspend publish failed org_id=%s attempt=%s error_class=%s",
                    org_id,
                    attempt + 1,
                    type(exc).__name__,
                )
                if attempt >= _PUBLISH_MAX_ATTEMPTS - 1:
                    raise
                await asyncio.sleep(_publish_backoff_seconds(attempt))
        if last_exc is not None:
            raise last_exc

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def org_suspend_payload(org_id: str) -> dict[str, object]:
    return {
        "v": 1,
        "event_type": "org_suspend",
        "org_id": org_id,
        "revoked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
