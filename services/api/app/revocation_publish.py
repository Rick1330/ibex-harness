"""Publish org_suspend events on the ADR-0029 revocation channel."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Protocol

logger = logging.getLogger(__name__)

REVOCATION_CHANNEL = "ibex:token:revocations"


class OrgSuspendPublisher(Protocol):
    async def publish_org_suspend(self, org_id: str) -> None: ...


class NoopOrgSuspendPublisher:
    async def publish_org_suspend(self, org_id: str) -> None:
        del org_id


class RecordingOrgSuspendPublisher:
    """Test double that records published org IDs and payloads."""

    def __init__(self) -> None:
        self.org_ids: list[str] = []
        self.payloads: list[dict[str, object]] = []

    async def publish_org_suspend(self, org_id: str) -> None:
        payload = org_suspend_payload(org_id)
        self.org_ids.append(org_id)
        self.payloads.append(payload)


class RedisOrgSuspendPublisher:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client = None

    async def _get_client(self):
        if self._client is None:
            from redis.asyncio import Redis

            self._client = Redis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def publish_org_suspend(self, org_id: str) -> None:
        payload = org_suspend_payload(org_id)
        try:
            client = await self._get_client()
            await client.publish(
                REVOCATION_CHANNEL, json.dumps(payload, separators=(",", ":"))
            )
        except Exception as exc:  # noqa: BLE001 — best-effort publish
            logger.warning(
                "org_suspend publish failed org_id=%s error_class=%s",
                org_id,
                type(exc).__name__,
            )

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
