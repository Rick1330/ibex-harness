"""Schema and Redis publisher tests for org model policies (m4.C.2)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.model_policy_publish import (
    NoopModelPolicyPublisher,
    RecordingModelPolicyPublisher,
    RedisModelPolicyPublisher,
    _redis_from_url,
)
from app.schemas.model_policies import ModelPolicyCreate, ModelPolicyPatch

_GOLDEN = (
    Path(__file__).resolve().parents[4]
    / "packages"
    / "modelpolicy"
    / "testdata"
    / "model_pattern_golden.json"
)


def _golden() -> dict:
    return json.loads(_GOLDEN.read_text(encoding="utf-8"))


@pytest.mark.parametrize("pattern", _golden()["accept"])
def test_create_accepts_golden_patterns(pattern: str) -> None:
    body = ModelPolicyCreate(model_pattern=pattern, allowed=True)
    assert body.model_pattern == pattern


@pytest.mark.parametrize("pattern", _golden()["reject"])
def test_create_rejects_golden_patterns(pattern: str) -> None:
    with pytest.raises(ValidationError):
        ModelPolicyCreate(model_pattern=pattern, allowed=True)


def test_create_rejects_whitespace_only() -> None:
    with pytest.raises(ValidationError):
        ModelPolicyCreate(model_pattern="   ", allowed=True)


def test_create_rejects_pattern_over_256_chars() -> None:
    with pytest.raises(ValidationError) as exc:
        ModelPolicyCreate(model_pattern="a" * 257, allowed=False)
    assert "256" in str(exc.value)


def test_create_strips_pattern() -> None:
    body = ModelPolicyCreate(model_pattern="  claude-*  ", allowed=True)
    assert body.model_pattern == "claude-*"


def test_patch_omitted_pattern_stays_none() -> None:
    body = ModelPolicyPatch(allowed=False)
    assert body.model_pattern is None
    assert body.allowed is False


def test_patch_explicit_none_pattern_stays_none() -> None:
    body = ModelPolicyPatch(model_pattern=None, priority=3)
    assert body.model_pattern is None
    assert body.priority == 3


def test_patch_rejects_empty_character_class() -> None:
    with pytest.raises(ValidationError):
        ModelPolicyPatch(model_pattern="[]")


@pytest.mark.asyncio
async def test_publishers_noop_and_recording() -> None:
    await NoopModelPolicyPublisher().publish_policy_update("ignored")
    recording = RecordingModelPolicyPublisher()
    await recording.publish_policy_update("org-1")
    assert recording.published == ["org-1"]


class _FakeRedis:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel, payload):
        self.published.append((channel, payload))

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_redis_publisher_channel_payload_and_aclose() -> None:
    fake = _FakeRedis()
    publisher = RedisModelPolicyPublisher("redis://localhost:6379/0")
    publisher._client = fake  # type: ignore[assignment]
    org_id = "550e8400-e29b-41d4-a716-446655440001"
    await publisher.publish_policy_update(org_id)
    channel, payload = fake.published[0]
    assert channel == f"model_policy_updates:{org_id}"
    assert '"v":1' in payload.replace(" ", "")
    assert org_id in payload
    await publisher.aclose()
    assert publisher._client is None


def test_redis_publisher_lazy_client() -> None:
    publisher = RedisModelPolicyPublisher("redis://localhost:6379/15")
    with patch("app.model_policy_publish._redis_from_url") as factory:
        factory.return_value = _FakeRedis()
        first = publisher._get_client()
        second = publisher._get_client()
        assert first is second
        factory.assert_called_once()


def test_redis_from_url_passes_timeouts() -> None:
    with patch("redis.asyncio.Redis.from_url") as from_url:
        from_url.return_value = object()
        client = _redis_from_url("redis://localhost:6379/0")
        assert client is from_url.return_value
        kwargs = from_url.call_args.kwargs
        assert kwargs["decode_responses"] is True
        assert kwargs["socket_timeout"] == 1.0
        assert kwargs["socket_connect_timeout"] == 1.0
