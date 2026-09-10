"""Unit tests for rate-limit configuration routes (m4.B.2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from authclient.permissions import MEMORY_READ
from apierror_py import INSUFFICIENT_PERMISSIONS, NOT_FOUND, VALIDATION_ERROR

from app.auth.client import ValidateResult
from app.errors import ApiError
from app.rate_limit_publish import (
    NoopRateLimitConfigPublisher,
    RecordingRateLimitConfigPublisher,
    RedisRateLimitConfigPublisher,
    RedisRateLimitCounter,
)
from app.schemas.rate_limits import RateLimitsPatchRequest, RateLimitsResponse
from app.services import rate_limits as rate_limit_service
from tests.unit.org_user_test_support import (
    ManagedClientOpts,
    bearer_headers,
    managed_org_client,
    owner_result,
)


def test_get_rate_limits_defaults() -> None:
    org_id = uuid4()
    counter = RedisRateLimitCounter(None)
    with (
        managed_org_client(ManagedClientOpts(org_id=org_id)) as (client, _, _),
        patch(
            "app.services.rate_limits.get_rate_limits",
            new=AsyncMock(
                return_value=RateLimitsResponse(
                    org_id=org_id,
                    requests_per_minute=60,
                    source="default",
                    platform_default_rpm=60,
                    current_minute_requests=0,
                    agent_overrides=[],
                )
            ),
        ),
    ):
        resp = client.get(
            f"/v1/organizations/{org_id}/rate-limits", headers=bearer_headers()
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["requests_per_minute"] == 60
    assert body["source"] == "default"
    assert body["current_minute_requests"] == 0
    del counter


def test_patch_rate_limits_owner_ok() -> None:
    org_id = uuid4()
    pub = RecordingRateLimitConfigPublisher()
    with (
        managed_org_client(ManagedClientOpts(org_id=org_id)) as (client, _, _),
        patch(
            "app.services.rate_limits.patch_rate_limits",
            new=AsyncMock(
                return_value=RateLimitsResponse(
                    org_id=org_id,
                    requests_per_minute=120,
                    source="override",
                    platform_default_rpm=60,
                    current_minute_requests=3,
                    agent_overrides=[],
                )
            ),
        ) as patched,
    ):
        client.app.state.api.rate_limit_config_publisher = pub
        resp = client.patch(
            f"/v1/organizations/{org_id}/rate-limits",
            headers=bearer_headers(),
            json={"requests_per_minute": 120},
        )
    assert resp.status_code == 200
    assert resp.json()["requests_per_minute"] == 120
    assert patched.await_count == 1


def test_member_and_viewer_patch_denied() -> None:
    org_id = uuid4()
    for role in ("member", "viewer"):
        with managed_org_client(
            ManagedClientOpts(
                org_id=org_id,
                role=role,
                result=ValidateResult(
                    org_id=org_id,
                    permissions=MEMORY_READ,
                    user_id=str(uuid4()),
                ),
            )
        ) as (client, _, _):
            resp = client.patch(
                f"/v1/organizations/{org_id}/rate-limits",
                headers=bearer_headers(),
                json={"requests_per_minute": 10},
            )
        assert resp.status_code == 403, role
        assert resp.json()["error"]["code"] == INSUFFICIENT_PERMISSIONS


def test_admin_patch_allowed() -> None:
    org_id = uuid4()
    with (
        managed_org_client(ManagedClientOpts(org_id=org_id, role="admin")) as (
            client,
            _,
            _,
        ),
        patch(
            "app.services.rate_limits.patch_rate_limits",
            new=AsyncMock(
                return_value=RateLimitsResponse(
                    org_id=org_id,
                    requests_per_minute=90,
                    source="override",
                    platform_default_rpm=60,
                    current_minute_requests=0,
                )
            ),
        ),
    ):
        resp = client.patch(
            f"/v1/organizations/{org_id}/rate-limits",
            headers=bearer_headers(),
            json={"requests_per_minute": 90},
        )
    assert resp.status_code == 200


def test_TestAPI_ISO_RATELIMIT_get_foreign_org_404() -> None:
    token_org = uuid4()
    other_org = uuid4()
    with managed_org_client(
        ManagedClientOpts(org_id=token_org, result=owner_result(org_id=token_org))
    ) as (client, _, _):
        resp = client.get(
            f"/v1/organizations/{other_org}/rate-limits", headers=bearer_headers()
        )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == NOT_FOUND


def test_TestAPI_ISO_RATELIMIT_patch_foreign_org_404() -> None:
    token_org = uuid4()
    other_org = uuid4()
    with managed_org_client(
        ManagedClientOpts(org_id=token_org, result=owner_result(org_id=token_org))
    ) as (client, _, _):
        resp = client.patch(
            f"/v1/organizations/{other_org}/rate-limits",
            headers=bearer_headers(),
            json={"requests_per_minute": 5},
        )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == NOT_FOUND


@pytest.mark.asyncio
async def test_get_rate_limits_service_maps_rows() -> None:
    org_id = uuid4()
    agent_id = uuid4()

    class _Rows:
        def all(self):
            return [(None, 150), (agent_id, 30)]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Rows())
    counter = AsyncMock()
    counter.org_current_minute_requests = AsyncMock(return_value=7)
    got = await rate_limit_service.get_rate_limits(
        session, org_id, platform_default_rpm=60, counter=counter
    )
    assert got.requests_per_minute == 150
    assert got.source == "override"
    assert got.current_minute_requests == 7
    assert len(got.agent_overrides) == 1
    assert got.agent_overrides[0].requests_per_minute == 30


@pytest.mark.asyncio
async def test_patch_rate_limits_publish_failure_does_not_raise() -> None:
    org_id = uuid4()
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            MagicMock(),  # upsert org
            MagicMock(all=lambda: [(None, 80)]),  # get list
        ]
    )
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    class _Boom:
        async def publish_config_update(self, _org_id: str) -> None:
            raise RuntimeError("redis down")

    counter = AsyncMock()
    counter.org_current_minute_requests = AsyncMock(return_value=0)
    body = RateLimitsPatchRequest(requests_per_minute=80)
    got = await rate_limit_service.patch_rate_limits(
        session,
        org_id,
        body,
        platform_default_rpm=60,
        counter=counter,
        publisher=_Boom(),
    )
    assert got.requests_per_minute == 80
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_patch_clear_org_and_agent_validation() -> None:
    org_id = uuid4()
    session = AsyncMock()
    with pytest.raises(ApiError) as exc:
        await rate_limit_service.patch_rate_limits(
            session,
            org_id,
            RateLimitsPatchRequest(requests_per_minute=10, clear_org_override=True),
            platform_default_rpm=60,
            counter=AsyncMock(),
            publisher=NoopRateLimitConfigPublisher(),
        )
    assert exc.value.code == VALIDATION_ERROR


@pytest.mark.asyncio
async def test_patch_unknown_agent_404() -> None:
    org_id = uuid4()
    agent_id = uuid4()

    class _ScalarNone:
        def scalar_one_or_none(self):
            return None

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarNone())
    with pytest.raises(ApiError) as exc:
        await rate_limit_service.patch_rate_limits(
            session,
            org_id,
            RateLimitsPatchRequest(
                agent_overrides=[{"agent_id": agent_id, "requests_per_minute": 5}]
            ),
            platform_default_rpm=60,
            counter=AsyncMock(),
            publisher=NoopRateLimitConfigPublisher(),
        )
    assert exc.value.code == NOT_FOUND


@pytest.mark.asyncio
async def test_patch_agent_upsert_and_clear() -> None:
    org_id = uuid4()
    agent_id = uuid4()

    class _ScalarOK:
        def scalar_one_or_none(self):
            return 1

    class _Rows:
        def all(self):
            return []

    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _ScalarOK(),  # agent exists (upsert path)
            MagicMock(),  # upsert agent
            _Rows(),  # list after upsert
            MagicMock(),  # delete org (clear_org_override)
            _ScalarOK(),  # agent exists (clear path)
            MagicMock(),  # delete agent
            _Rows(),  # list after clear
        ]
    )
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    counter = AsyncMock()
    counter.org_current_minute_requests = AsyncMock(return_value=0)
    pub = RecordingRateLimitConfigPublisher()
    await rate_limit_service.patch_rate_limits(
        session,
        org_id,
        RateLimitsPatchRequest(
            agent_overrides=[{"agent_id": agent_id, "requests_per_minute": 11}]
        ),
        platform_default_rpm=60,
        counter=counter,
        publisher=pub,
    )
    await rate_limit_service.patch_rate_limits(
        session,
        org_id,
        RateLimitsPatchRequest(
            agent_overrides=[{"agent_id": agent_id, "requests_per_minute": None}],
            clear_org_override=True,
        ),
        platform_default_rpm=60,
        counter=counter,
        publisher=pub,
    )
    assert pub.published == [str(org_id), str(org_id)]


@pytest.mark.asyncio
async def test_counter_get_errors_and_bad_values() -> None:
    class _Client:
        async def get(self, _key):
            raise RuntimeError("boom")

        async def aclose(self):
            return None

    counter = RedisRateLimitCounter("redis://x")
    counter._client = _Client()  # type: ignore[assignment]
    assert await counter.org_current_minute_requests("o") == 0

    class _Bad:
        async def get(self, _key):
            return "x"

        async def aclose(self):
            return None

    counter2 = RedisRateLimitCounter("redis://x")
    counter2._client = _Bad()  # type: ignore[assignment]
    assert await counter2.org_current_minute_requests("o") == 0


def test_router_uses_settings_defaults() -> None:
    org_id = uuid4()
    with (
        managed_org_client(ManagedClientOpts(org_id=org_id)) as (client, _, _),
        patch(
            "app.services.rate_limits.get_rate_limits",
            new=AsyncMock(
                return_value=RateLimitsResponse(
                    org_id=org_id,
                    requests_per_minute=60,
                    source="default",
                    platform_default_rpm=60,
                    current_minute_requests=0,
                )
            ),
        ),
    ):
        client.app.state.api.settings = None
        resp = client.get(
            f"/v1/organizations/{org_id}/rate-limits", headers=bearer_headers()
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_noop_and_recording_publishers() -> None:
    await NoopRateLimitConfigPublisher().publish_config_update("x")
    rec = RecordingRateLimitConfigPublisher()
    await rec.publish_config_update("y")
    assert rec.published == ["y"]

    published: list[tuple[str, str]] = []

    class _Client:
        async def publish(self, channel, payload):
            published.append((channel, payload))

        async def get(self, key):
            if key.endswith(":rpm:1"):
                return "9"
            return None

        async def aclose(self):
            return None

    pub = RedisRateLimitConfigPublisher("redis://localhost:6379/0")
    pub._client = _Client()  # type: ignore[assignment]
    await pub.publish_config_update("550e8400-e29b-41d4-a716-446655440001")
    assert published[0][0].startswith("ratelimit_config_updates:")
    assert '"v": 1' in published[0][1] or '"v":1' in published[0][1].replace(" ", "")

    counter = RedisRateLimitCounter("redis://localhost:6379/0")
    counter._client = _Client()  # type: ignore[assignment]
    with patch("time.time", return_value=60):
        assert await counter.org_current_minute_requests("org") == 9
    assert await RedisRateLimitCounter(None).org_current_minute_requests("org") == 0
    await pub.aclose()
    await counter.aclose()
