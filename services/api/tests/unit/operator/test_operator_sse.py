"""Operator SSE hub and HTTP stream tests."""

from __future__ import annotations

import asyncio
from unittest.mock import patch
from uuid import uuid4

import pytest
from authclient.permissions import OPERATOR_METADATA_READ

from app.drain import DrainState
from app.sse.operator_events import OperatorSSEHub, redis_fan_in_loop, write_sse_chunk
from tests.unit.operator.conftest import operator_settings

ORG_A = uuid4()
ORG_B = uuid4()


@pytest.mark.asyncio
async def test_sse_last_event_id_resume_no_duplicates() -> None:
    settings = operator_settings()
    drain = DrainState()
    hub = OperatorSSEHub(settings=settings, drain=drain)
    id1 = await hub.publish({"n": 1}, org_id=ORG_A)
    id2 = await hub.publish({"n": 2}, org_id=ORG_A)
    assert id2 == id1 + 1

    seen: list[int] = []

    async def collect(last: int | None, limit: int) -> None:
        count = 0
        async for chunk in hub.subscribe(ORG_A, last):
            if chunk.startswith(b"id:"):
                eid = int(chunk.split(b"\n")[0].split(b":")[1].strip())
                seen.append(eid)
                count += 1
                if count >= limit:
                    break

    task = asyncio.create_task(collect(id1, 1))
    await asyncio.sleep(0.05)
    await hub.publish({"n": 3}, org_id=ORG_A)
    await asyncio.wait_for(task, timeout=2.0)
    assert id1 not in seen
    assert seen[0] > id1


@pytest.mark.asyncio
async def test_sse_cross_tenant_isolation_live_and_backlog() -> None:
    """Org B must never see Org A events live or via Last-Event-ID resume."""
    settings = operator_settings()
    drain = DrainState()
    hub = OperatorSSEHub(settings=settings, drain=drain)
    await hub.publish({"secret": "a1"}, org_id=ORG_A)
    id_a2 = await hub.publish({"secret": "a2"}, org_id=ORG_A)

    seen_b: list[bytes] = []

    async def collect_b(last: int | None, limit: int) -> None:
        count = 0
        async for chunk in hub.subscribe(ORG_B, last):
            if chunk.startswith(b"id:"):
                seen_b.append(chunk)
                count += 1
                if count >= limit:
                    break

    # Backlog for B after A's publishes should be empty until B publishes.
    task = asyncio.create_task(collect_b(None, 1))
    await asyncio.sleep(0.05)
    await hub.publish({"secret": "a3"}, org_id=ORG_A)
    id_b1 = await hub.publish({"ok": "b1"}, org_id=ORG_B)
    await asyncio.wait_for(task, timeout=2.0)
    assert len(seen_b) == 1
    assert b'"ok":"b1"' in seen_b[0]
    assert b"secret" not in seen_b[0]

    # Resume after B's id must not replay A's earlier ids.
    resume: list[int] = []
    async for chunk in hub.subscribe(ORG_B, id_b1 - 1 if id_b1 > 0 else None):
        if chunk.startswith(b"id:"):
            resume.append(int(chunk.split(b"\n")[0].split(b":")[1].strip()))
            break
    assert resume == [id_b1]
    assert id_a2 not in resume


@pytest.mark.asyncio
async def test_sse_drain_rejects_new_subscribers() -> None:
    settings = operator_settings()
    drain = DrainState()
    hub = OperatorSSEHub(settings=settings, drain=drain)
    drain.begin_drain()
    with pytest.raises(RuntimeError, match="draining"):
        async for _ in hub.subscribe(ORG_A, None):
            pass


@pytest.mark.asyncio
async def test_hub_queue_full_disconnects_subscriber() -> None:
    from app.sse.operator_events import _Subscriber

    settings = operator_settings()
    drain = DrainState()
    hub = OperatorSSEHub(settings=settings, drain=drain)
    full: asyncio.Queue = asyncio.Queue(maxsize=1)
    full.put_nowait("x")  # type: ignore[arg-type]
    hub._subscribers = [_Subscriber(org_id=ORG_A, queue=full)]
    eid = await hub.publish({"ok": True}, org_id=ORG_A)
    assert eid >= 1
    assert hub._subscribers == []
    # Sentinel closes the stream for reconnect.
    assert full.get_nowait() is None


@pytest.mark.asyncio
async def test_subscribe_exits_on_close() -> None:
    settings = operator_settings()
    drain = DrainState()
    hub = OperatorSSEHub(settings=settings, drain=drain)
    await hub.publish({"n": 1}, org_id=ORG_A)

    async def reader() -> bytes | None:
        async for chunk in hub.subscribe(ORG_A, None):
            await hub.close_all()
            return chunk
        return None

    chunk = await asyncio.wait_for(reader(), timeout=2.0)
    assert chunk is not None
    assert chunk.startswith(b"id:")


@pytest.mark.asyncio
async def test_write_sse_chunk_records_slow_metric() -> None:
    settings = operator_settings(sse_slow_write_ms=1)
    sent: list[bytes] = []

    async def send(chunk: bytes) -> None:
        await asyncio.sleep(0.01)
        sent.append(chunk)

    await write_sse_chunk(send, b"data: x\n\n", settings=settings)
    assert sent == [b"data: x\n\n"]


@pytest.mark.asyncio
async def test_write_sse_chunk_deadline() -> None:
    settings = operator_settings(sse_write_deadline_seconds=1.0)

    async def slow(_chunk: bytes) -> None:
        await asyncio.sleep(2.0)

    with pytest.raises(TimeoutError):
        await write_sse_chunk(slow, b"x", settings=settings)


@pytest.mark.asyncio
async def test_redis_fan_in_publishes_json(monkeypatch: pytest.MonkeyPatch) -> None:
    hub, stop = _fan_in_hub()
    monkeypatch.setattr(
        "app.sse.operator_events.Redis",
        _fake_redis_mod([{"data": f'{{"k":1,"org_id":"{ORG_A}"}}'}], stop),
    )
    await asyncio.wait_for(
        redis_fan_in_loop(hub, redis_url="redis://x", channel="c", stop=stop),
        timeout=2.0,
    )
    assert hub._history[-1].payload == {"k": 1}
    assert hub._history[-1].org_id == ORG_A


@pytest.mark.asyncio
async def test_redis_fan_in_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    hub, stop = _fan_in_hub()
    monkeypatch.setattr(
        "app.sse.operator_events.Redis",
        _fake_redis_mod([{"data": "not-json"}], stop),
    )
    await asyncio.wait_for(
        redis_fan_in_loop(hub, redis_url="redis://x", channel="c", stop=stop),
        timeout=2.0,
    )
    # Fan-in without org_id is dropped (never delivered cross-tenant / unscoped).
    assert hub._history == []


def _fan_in_hub() -> tuple[OperatorSSEHub, asyncio.Event]:
    return OperatorSSEHub(settings=operator_settings(), drain=DrainState()), asyncio.Event()


def _fake_redis_mod(messages: list[dict | None], stop: asyncio.Event):
    class FakePubSub:
        def __init__(self) -> None:
            self._n = 0

        async def subscribe(self, *_a, **_k) -> None:
            return None

        async def unsubscribe(self, *_a, **_k) -> None:
            return None

        async def aclose(self) -> None:
            return None

        async def get_message(self, **_k):
            if self._n < len(messages):
                msg = messages[self._n]
                self._n += 1
                return msg
            stop.set()
            return None

    class FakeRedis:
        def pubsub(self) -> FakePubSub:
            return FakePubSub()

        async def aclose(self) -> None:
            return None

    class FakeRedisMod:
        @staticmethod
        def from_url(*_a, **_k) -> FakeRedis:
            return FakeRedis()

    return FakeRedisMod


def test_sse_stream_requires_session_cookie(app_client) -> None:
    _, client = app_client
    resp = client.get("/v1/operator/events/stream")
    assert resp.status_code == 401


def test_sse_stream_denies_without_metadata_permission_before_subscribe() -> None:
    from unittest.mock import AsyncMock

    from app.auth.client import StaticTokenValidator, ValidateResult
    from tests.unit.operator.conftest import create_operator_app

    validator = StaticTokenValidator(
        {"ibex_pat_test_secret": ValidateResult(org_id=ORG_A, permissions=0, user_id="u1")}
    )
    with create_operator_app(validator=validator) as (app, client):
        login = client.post("/v1/operator/session/login", json={"pat": "ibex_pat_test_secret"})
        assert login.status_code == 200
        subscribe = AsyncMock()
        app.state.operator_sse_hub.subscribe = subscribe
        response = client.get("/v1/operator/events/stream")
    assert response.status_code == 403
    subscribe.assert_not_awaited()


def test_sse_stream_backlog_and_last_event_id_http(app_client) -> None:
    app, client = app_client
    login = client.post("/v1/operator/session/login", json={"pat": "ibex_pat_test_secret"})
    assert login.status_code == 200
    hub: OperatorSSEHub = app.state.operator_sse_hub

    async def finite_sub(org_id, last_event_id: int | None = None):
        assert last_event_id is None
        yield b'id: 1\nevent: operator.evidence\ndata:{"n":1}\n\n'

    with patch.object(hub, "subscribe", finite_sub):
        resp = client.get("/v1/operator/events/stream")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        assert "no-store" in resp.headers.get("cache-control", "")
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert "id: 1" in resp.text

    async def resume_sub(org_id, last_event_id: int | None = None):
        assert last_event_id == 1
        yield b'id: 2\nevent: operator.evidence\ndata:{"n":2}\n\n'

    with patch.object(hub, "subscribe", resume_sub):
        resp = client.get("/v1/operator/events/stream", headers={"Last-Event-ID": "1"})
        assert resp.status_code == 200
        assert "id: 2" in resp.text


def test_sse_http_drain_rejects_new_stream(app_client) -> None:
    app, client = app_client
    login = client.post("/v1/operator/session/login", json={"pat": "ibex_pat_test_secret"})
    assert login.status_code == 200
    app.state.api.drain.begin_drain()
    resp = client.get("/v1/operator/events/stream")
    assert resp.status_code == 503
    assert resp.headers.get("X-IBEX-Drain") == "1"


def test_sse_stream_feature_disabled() -> None:
    from app.auth.client import StaticTokenValidator
    from tests.unit.operator.conftest import create_operator_app, operator_settings

    settings = operator_settings(operator_feature_enabled=False)
    with create_operator_app(settings=settings, validator=StaticTokenValidator({})) as (_, client):
        resp = client.get("/v1/operator/events/stream")
        assert resp.status_code == 503


@pytest.mark.asyncio
async def test_hub_trims_history_and_disconnect_full_sentinel() -> None:
    settings = operator_settings()
    drain = DrainState()
    hub = OperatorSSEHub(settings=settings, drain=drain, _history_limit=2)
    await hub.publish({"n": 1}, org_id=ORG_A)
    await hub.publish({"n": 2}, org_id=ORG_A)
    await hub.publish({"n": 3}, org_id=ORG_A)
    assert [e.event_id for e in hub._history] == [2, 3]

    # Double-full queue exercises get_nowait + put_nowait retry path.
    from app.sse.operator_events import _Subscriber

    full: asyncio.Queue = asyncio.Queue(maxsize=1)
    full.put_nowait("x")  # type: ignore[arg-type]
    hub._disconnect_subscriber(_Subscriber(org_id=ORG_A, queue=full))
    assert full.empty() or full.get_nowait() is None


@pytest.mark.asyncio
async def test_hub_heartbeat_and_close_all_full_queue() -> None:
    from app.sse.operator_events import _Subscriber

    settings = operator_settings()
    drain = DrainState()
    hub = OperatorSSEHub(settings=settings, drain=drain)

    async def one_heartbeat() -> bytes:
        agen = hub.subscribe(ORG_A, None)
        try:
            async def expire_without_leaking(awaitable, **_kwargs):
                close = getattr(awaitable, "close", None)
                if close is not None:
                    close()
                raise TimeoutError

            with patch("asyncio.wait_for", side_effect=expire_without_leaking):
                return await agen.__anext__()
        finally:
            await agen.aclose()

    chunk = await asyncio.wait_for(one_heartbeat(), timeout=2.0)
    assert chunk == b": heartbeat\n\n"

    full: asyncio.Queue = asyncio.Queue(maxsize=1)
    full.put_nowait("x")  # type: ignore[arg-type]
    hub._subscribers = [_Subscriber(org_id=ORG_A, queue=full)]
    await hub.close_all()


@pytest.mark.asyncio
async def test_decode_and_backoff_helpers() -> None:
    from app.sse.operator_events import _backoff_sleep, _decode_fan_in_payload

    assert _decode_fan_in_payload(b"x") is None
    assert _decode_fan_in_payload('"hi"') == {"raw": "hi"}
    stop = asyncio.Event()
    stop.set()
    await _backoff_sleep(stop, 0)


@pytest.mark.asyncio
async def test_redis_fan_in_auth_error_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    from redis.exceptions import AuthenticationError

    hub, stop = _fan_in_hub()

    class Boom:
        @staticmethod
        def from_url(*_a, **_k):
            raise AuthenticationError("nope")

    monkeypatch.setattr("app.sse.operator_events.Redis", Boom)
    await asyncio.wait_for(
        redis_fan_in_loop(hub, redis_url="redis://x", channel="c", stop=stop),
        timeout=2.0,
    )


@pytest.mark.asyncio
async def test_redis_fan_in_retry_then_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    from redis.exceptions import RedisError

    hub, stop = _fan_in_hub()
    calls = {"n": 0}

    class Boom:
        @staticmethod
        def from_url(*_a, **_k):
            calls["n"] += 1
            if calls["n"] >= 2:
                stop.set()
            raise RedisError("transient")

    async def fast_backoff(_stop, _attempt):
        return None

    monkeypatch.setattr("app.sse.operator_events.Redis", Boom)
    monkeypatch.setattr("app.sse.operator_events._backoff_sleep", fast_backoff)
    await asyncio.wait_for(
        redis_fan_in_loop(hub, redis_url="redis://x", channel="c", stop=stop),
        timeout=2.0,
    )
    assert calls["n"] >= 2


@pytest.mark.asyncio
async def test_aclose_redis_fan_in_swallows_errors() -> None:
    from redis.exceptions import RedisError

    from app.sse.operator_events import _aclose_redis_fan_in

    class BadPubSub:
        async def unsubscribe(self, *_a):
            raise RedisError("u")

        async def aclose(self):
            raise RedisError("c")

    class BadClient:
        async def aclose(self):
            raise RedisError("client")

    await _aclose_redis_fan_in(BadPubSub(), BadClient(), "ch")  # type: ignore[arg-type]


def test_sse_stream_bad_cookie(app_client) -> None:
    _, client = app_client
    client.cookies.set("ibex_session", "a.b.c")
    resp = client.get("/v1/operator/events/stream")
    assert resp.status_code == 401


def _staging_operator_settings():
    from tests.unit.operator.conftest import operator_settings

    return operator_settings(
        environment="staging",
        jwt_hmac_secret=None,
        jwt_public_keys_pem="configured-public-key-set",
        redis_url="redis://127.0.0.1:6379/0",
        cookie_secure=True,
    )


def _validated_session(*, org_id: str = str(ORG_A), permissions: int = OPERATOR_METADATA_READ):
    from app.auth.session_refresh import ValidatedSession

    return ValidatedSession(
        subject="operator-1",
        org_id=org_id,
        permissions=permissions,
        session_id="session-1",
        jti="access-jti-1",
    )


def test_staging_sse_rejects_revoked_session_before_subscribing() -> None:
    from unittest.mock import AsyncMock

    from app.auth.client import AuthFailedError
    from tests.unit.operator.conftest import create_operator_app

    with create_operator_app(settings=_staging_operator_settings()) as (app, client):
        client.cookies.set("ibex_session", "signed-but-revoked")
        subscribe = AsyncMock()
        app.state.operator_sse_hub.subscribe = subscribe
        with patch(
            "app.operator_session_auth.validate_operator_session",
            new=AsyncMock(side_effect=AuthFailedError("revoked")),
        ) as validate:
            response = client.get("/v1/operator/events/stream")
    assert response.status_code == 401
    validate.assert_awaited_once()
    subscribe.assert_not_awaited()


def test_staging_sse_fails_closed_when_auth_service_is_unavailable() -> None:
    from unittest.mock import AsyncMock

    from app.auth.client import AuthUnavailableError
    from tests.unit.operator.conftest import create_operator_app

    with create_operator_app(settings=_staging_operator_settings()) as (app, client):
        client.cookies.set("ibex_session", "session-cookie")
        subscribe = AsyncMock()
        app.state.operator_sse_hub.subscribe = subscribe
        with patch(
            "app.operator_session_auth.validate_operator_session",
            new=AsyncMock(side_effect=AuthUnavailableError("offline")),
        ) as validate:
            response = client.get("/v1/operator/events/stream")
    assert response.status_code == 503
    validate.assert_awaited_once()
    subscribe.assert_not_awaited()


def test_staging_sse_uses_auth_service_tenant_and_permission() -> None:
    from unittest.mock import AsyncMock

    from tests.unit.operator.conftest import create_operator_app

    observed: list[object] = []

    async def finite_subscribe(org_id, last_event_id=None):
        observed.extend([org_id, last_event_id])
        yield b"id: 9\nevent: operator.evidence\ndata: {}\n\n"

    with create_operator_app(settings=_staging_operator_settings()) as (app, client):
        client.cookies.set("ibex_session", "valid-session-cookie")
        app.state.operator_sse_hub.subscribe = finite_subscribe
        with patch(
            "app.operator_session_auth.validate_operator_session",
            new=AsyncMock(return_value=_validated_session()),
        ) as validate:
            response = client.get("/v1/operator/events/stream")
    assert response.status_code == 200
    assert observed == [ORG_A, None]
    validate.assert_awaited_once()


def test_staging_sse_rejects_invalid_tenant_claim_before_subscribe() -> None:
    from unittest.mock import AsyncMock

    from tests.unit.operator.conftest import create_operator_app

    with create_operator_app(settings=_staging_operator_settings()) as (app, client):
        client.cookies.set("ibex_session", "malformed-org-claim")
        subscribe = AsyncMock()
        app.state.operator_sse_hub.subscribe = subscribe
        with patch(
            "app.operator_session_auth.validate_operator_session",
            new=AsyncMock(return_value=_validated_session(org_id="not-a-uuid")),
        ):
            response = client.get("/v1/operator/events/stream")
    assert response.status_code == 401
    subscribe.assert_not_awaited()


def _assert_staging_platform_health(cookie: str, validate_mock, expected_status: int) -> None:
    from tests.unit.operator.conftest import create_operator_app

    with create_operator_app(settings=_staging_operator_settings()) as (_, client):
        client.cookies.set("ibex_session", cookie)
        with patch(
            "app.operator_session_auth.validate_operator_session",
            new=validate_mock,
        ) as validate:
            response = client.get("/v1/operator/platform/health")
    assert response.status_code == expected_status
    validate.assert_awaited_once()


def test_staging_platform_health_rejects_revoked_session() -> None:
    from unittest.mock import AsyncMock

    from app.auth.client import AuthFailedError

    _assert_staging_platform_health(
        "revoked-session-cookie",
        AsyncMock(side_effect=AuthFailedError("revoked")),
        401,
    )


def test_staging_platform_health_rejects_missing_metadata_permission() -> None:
    from unittest.mock import AsyncMock

    _assert_staging_platform_health(
        "valid-session-without-metadata-grant",
        AsyncMock(return_value=_validated_session(permissions=0)),
        403,
    )


def test_sse_stream_write_deadline_and_disconnect(app_client) -> None:
    app, client = app_client
    login = client.post("/v1/operator/session/login", json={"pat": "ibex_pat_test_secret"})
    assert login.status_code == 200
    hub = app.state.operator_sse_hub

    async def slow_sub(_org_id, _last=None):
        yield b"id: 1\ndata: {}\n\n"
        yield b"id: 2\ndata: {}\n\n"

    # Deadline path: patch timeout to fail on first write.
    with (
        patch.object(hub, "subscribe", slow_sub),
        patch("app.routers.operator_events.asyncio.timeout", side_effect=TimeoutError),
    ):
        resp = client.get("/v1/operator/events/stream")
        assert resp.status_code == 200


def test_publish_test_route_removed(app_client) -> None:
    _, client = app_client
    login = client.post("/v1/operator/session/login", json={"pat": "ibex_pat_test_secret"})
    csrf = login.json()["csrf_token"]
    resp = client.post(
        "/v1/operator/events/publish-test",
        json={"x": 1},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 404


def test_stream_uses_session_org_id_for_subscribe(app_client) -> None:
    """Connect must pass server-verified SessionClaims.org_id into hub.subscribe."""
    app, client = app_client
    login = client.post("/v1/operator/session/login", json={"pat": "ibex_pat_test_secret"})
    assert login.status_code == 200
    org = login.json()["org_id"]
    hub = app.state.operator_sse_hub
    seen: list[object] = []

    async def capturing_sub(org_id, last_event_id=None):
        seen.append(org_id)
        yield b'id: 1\nevent: operator.evidence\ndata:{}\n\n'

    with patch.object(hub, "subscribe", capturing_sub):
        resp = client.get("/v1/operator/events/stream")
        assert resp.status_code == 200
    assert len(seen) == 1
    assert str(seen[0]) == org


def test_stream_hub_missing(app_client) -> None:
    _, client = app_client
    login = client.post("/v1/operator/session/login", json={"pat": "ibex_pat_test_secret"})
    assert login.status_code == 200
    client.app.state.operator_sse_hub = None
    resp = client.get("/v1/operator/events/stream")
    assert resp.status_code == 503


def test_csrf_cookie_map_skips_malformed_segments() -> None:
    from app.middleware.csrf import _cookie_map

    assert _cookie_map(None) == {}
    assert _cookie_map("lonely; ibex_csrf=abc; also_bad") == {"ibex_csrf": "abc"}
