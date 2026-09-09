"""Unit tests for org suspend publish payload and publishers."""

from __future__ import annotations

import pytest

from app.revocation_publish import (
    NoopOrgSuspendPublisher,
    RecordingOrgSuspendPublisher,
    RedisOrgSuspendPublisher,
    org_suspend_payload,
)


@pytest.mark.asyncio
async def test_org_suspend_payload_shape() -> None:
    payload = org_suspend_payload("11111111-1111-4111-8111-111111111111")
    assert payload["v"] == 1
    assert payload["event_type"] == "org_suspend"
    assert payload["org_id"] == "11111111-1111-4111-8111-111111111111"
    assert isinstance(payload["revoked_at"], str)
    assert str(payload["revoked_at"]).endswith("Z")


@pytest.mark.asyncio
async def test_recording_publisher() -> None:
    pub = RecordingOrgSuspendPublisher()
    await pub.publish_org_suspend("org-1")
    assert pub.org_ids == ["org-1"]
    assert pub.payloads[0]["event_type"] == "org_suspend"


@pytest.mark.asyncio
async def test_noop_publisher() -> None:
    await NoopOrgSuspendPublisher().publish_org_suspend("org-1")


@pytest.mark.asyncio
async def test_redis_publisher_swallows_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    pub = RedisOrgSuspendPublisher("redis://localhost:6379/0")

    class _Boom:
        async def publish(self, *_a, **_k):
            raise OSError("down")

    async def _client():
        return _Boom()

    monkeypatch.setattr(pub, "_get_client", _client)
    await pub.publish_org_suspend("org-1")


@pytest.mark.asyncio
async def test_redis_publisher_aclose(monkeypatch: pytest.MonkeyPatch) -> None:
    pub = RedisOrgSuspendPublisher("redis://localhost:6379/0")

    class _Client:
        async def aclose(self):
            self.closed = True

        async def publish(self, *_a, **_k):
            return 1

    client = _Client()

    async def _get():
        return client

    monkeypatch.setattr(pub, "_get_client", _get)
    pub._client = client
    await pub.aclose()
    assert pub._client is None
