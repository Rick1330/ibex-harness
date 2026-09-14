"""Operator-event SSE hub — independent of proxy stream_forward / ADR-0027."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from prometheus_client import Counter, Histogram
from redis.asyncio import Redis
from redis.exceptions import AuthenticationError, RedisError

from app.config import Settings
from app.drain import DrainState

logger = logging.getLogger(__name__)

SSE_SLOW_WRITES = Counter(
    "ibex_api_operator_sse_slow_writes_total",
    "Operator SSE write+flush slower than threshold",
)
SSE_WRITE_SECONDS = Histogram(
    "ibex_api_operator_sse_write_seconds",
    "Operator SSE event write duration",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0),
)

_FAN_IN_BACKOFF_BASE_S = 0.5
_FAN_IN_BACKOFF_MAX_S = 30.0
_FAN_IN_BACKOFF_MAX_ATTEMPT = 6  # 0.5 * 2^6 = 32 > max; clamp beyond this
_RNG = secrets.SystemRandom()


@dataclass
class OperatorEvent:
    event_id: int
    org_id: UUID
    payload: dict[str, Any]
    event_type: str = "operator.evidence"


@dataclass
class _Subscriber:
    org_id: UUID
    queue: asyncio.Queue[OperatorEvent | None]


@dataclass
class OperatorSSEHub:
    """In-process ring buffer + optional Redis fan-in for operator-event SSE."""

    settings: Settings
    drain: DrainState
    _next_id: int = 1
    _history: list[OperatorEvent] = field(default_factory=list)
    _subscribers: list[_Subscriber] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _history_limit: int = 256

    async def publish(
        self,
        payload: dict[str, Any],
        *,
        org_id: UUID,
        event_type: str = "operator.evidence",
    ) -> int:
        if not isinstance(org_id, UUID):
            raise TypeError("org_id is required for operator SSE publish")
        async with self._lock:
            event = OperatorEvent(
                event_id=self._next_id,
                org_id=org_id,
                payload=payload,
                event_type=event_type,
            )
            self._next_id += 1
            self._history.append(event)
            if len(self._history) > self._history_limit:
                self._history = self._history[-self._history_limit :]
            lagging: list[_Subscriber] = []
            for sub in self._subscribers:
                if sub.org_id != org_id:
                    continue
                try:
                    sub.queue.put_nowait(event)
                except asyncio.QueueFull:
                    lagging.append(sub)
            for sub in lagging:
                self._disconnect_subscriber(sub)
            return event.event_id

    def _force_sentinel(self, queue: asyncio.Queue[OperatorEvent | None]) -> None:
        try:
            queue.put_nowait(None)
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                return

    def _disconnect_subscriber(self, sub: _Subscriber) -> None:
        """Drop a lagging subscriber so the client reconnects with Last-Event-ID."""
        logger.warning("operator sse subscriber queue full; disconnecting stream")
        if sub in self._subscribers:
            self._subscribers.remove(sub)
        try:
            sub.queue.put_nowait(None)
        except asyncio.QueueFull:
            self._force_sentinel(sub.queue)

    def _backlog_after(self, org_id: UUID, last_event_id: int | None) -> list[OperatorEvent]:
        scoped = [e for e in self._history if e.org_id == org_id]
        if last_event_id is None:
            return scoped
        return [e for e in scoped if e.event_id > last_event_id]

    async def _live_chunks(
        self, queue: asyncio.Queue[OperatorEvent | None]
    ) -> AsyncIterator[bytes]:
        while not self.drain.draining:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=15.0)
            except TimeoutError:
                yield b": heartbeat\n\n"
                continue
            if item is None:
                return
            yield self._format_event(item)

    async def subscribe(self, org_id: UUID, last_event_id: int | None) -> AsyncIterator[bytes]:
        if not isinstance(org_id, UUID):
            raise TypeError("org_id is required for operator SSE subscribe")
        if self.drain.draining:
            raise RuntimeError("draining")
        queue: asyncio.Queue[OperatorEvent | None] = asyncio.Queue(maxsize=64)
        sub = _Subscriber(org_id=org_id, queue=queue)
        async with self._lock:
            backlog = self._backlog_after(org_id, last_event_id)
            self._subscribers.append(sub)
        try:
            for event in backlog:
                yield self._format_event(event)
            async for chunk in self._live_chunks(queue):
                yield chunk
        finally:
            async with self._lock:
                if sub in self._subscribers:
                    self._subscribers.remove(sub)

    def _format_event(self, event: OperatorEvent) -> bytes:
        data = json.dumps(event.payload, separators=(",", ":"))
        return f"id: {event.event_id}\nevent: {event.event_type}\ndata: {data}\n\n".encode()

    async def close_all(self) -> None:
        async with self._lock:
            for sub in self._subscribers:
                try:
                    sub.queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass


async def write_sse_chunk(
    send_bytes,
    chunk: bytes,
    *,
    settings: Settings,
) -> None:
    """Write one SSE chunk with a finite deadline and slow-write metric (F4-033)."""
    started = time.perf_counter()
    try:
        await asyncio.wait_for(send_bytes(chunk), timeout=settings.sse_write_deadline_seconds)
    except TimeoutError as exc:
        raise TimeoutError("operator sse write deadline exceeded") from exc
    finally:
        elapsed = time.perf_counter() - started
        SSE_WRITE_SECONDS.observe(elapsed)
        if elapsed * 1000 >= settings.sse_slow_write_ms:
            SSE_SLOW_WRITES.inc()


def _decode_fan_in_payload(data: object) -> dict[str, Any] | None:
    if not isinstance(data, str):
        return None
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return {"raw": data}
    if isinstance(payload, dict):
        return payload
    return {"raw": payload}


async def _backoff_sleep(stop: asyncio.Event, attempt: int) -> None:
    exp = min(max(attempt, 0), _FAN_IN_BACKOFF_MAX_ATTEMPT)
    delay = min(_FAN_IN_BACKOFF_BASE_S * (2**exp), _FAN_IN_BACKOFF_MAX_S)
    delay += _RNG.uniform(0, delay * 0.25)
    try:
        await asyncio.wait_for(stop.wait(), timeout=delay)
    except TimeoutError:
        return


async def _connect_pubsub(redis_url: str, channel: str) -> tuple[Redis, Any]:
    client = Redis.from_url(redis_url, decode_responses=True)
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(channel)
    except Exception:
        await _aclose_redis_fan_in(pubsub, client, channel)
        raise
    return client, pubsub


def _org_id_from_fan_in_payload(payload: dict[str, Any]) -> UUID | None:
    """Require a valid org_id on Redis fan-in payloads; drop otherwise."""
    org_raw = payload.pop("org_id", None)
    if org_raw is None:
        logger.warning("operator sse redis fan-in dropped event without org_id")
        return None
    try:
        return UUID(str(org_raw))
    except ValueError:
        logger.warning("operator sse redis fan-in dropped event with invalid org_id")
        return None


async def _fan_in_get_message(pubsub: Any) -> dict[str, Any] | None:
    try:
        return await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
    except asyncio.CancelledError:
        raise
    except (OSError, RedisError) as exc:
        raise RedisError(str(exc)) from exc


async def _fan_in_publish_message(hub: OperatorSSEHub, message: dict[str, Any]) -> None:
    payload = _decode_fan_in_payload(message.get("data"))
    if payload is None:
        return
    org_id = _org_id_from_fan_in_payload(payload)
    if org_id is None:
        return
    await hub.publish(payload, org_id=org_id)


async def _fan_in_read_loop(
    hub: OperatorSSEHub,
    pubsub: Any,
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        message = await _fan_in_get_message(pubsub)
        if message is None:
            await asyncio.sleep(0.05)
            continue
        await _fan_in_publish_message(hub, message)


async def _safe_await(label: str, coro_factory: Callable[[], Awaitable[Any]]) -> None:
    try:
        await coro_factory()
    except (OSError, RedisError) as exc:
        logger.debug("redis fan-in %s: %s", label, exc)


async def _safe_unsubscribe(pubsub: object, channel: str) -> None:
    unsubscribe = getattr(pubsub, "unsubscribe", None)
    if unsubscribe is None:
        return
    await _safe_await("unsubscribe", lambda: unsubscribe(channel))


async def _safe_aclose(obj: object, label: str) -> None:
    closer = getattr(obj, "aclose", None)
    if closer is None:
        return
    await _safe_await(label, closer)


async def _aclose_redis_fan_in(pubsub: object | None, client: Redis | None, channel: str) -> None:
    if pubsub is not None:
        await _safe_unsubscribe(pubsub, channel)
        await _safe_aclose(pubsub, "pubsub close")
    if client is not None:
        await _safe_aclose(client, "client close")


async def redis_fan_in_loop(
    hub: OperatorSSEHub,
    *,
    redis_url: str,
    channel: str,
    stop: asyncio.Event,
) -> None:
    """Subscribe to Redis pub/sub with retry/backoff; forward into the hub."""
    attempt = 0
    while not stop.is_set():
        client: Redis | None = None
        pubsub = None
        try:
            client, pubsub = await _connect_pubsub(redis_url, channel)
            attempt = 0
            await _fan_in_read_loop(hub, pubsub, stop)
        except asyncio.CancelledError:
            raise
        except AuthenticationError:
            logger.exception("operator sse redis fan-in auth failed")
            return
        except (OSError, RedisError) as exc:
            logger.warning("operator sse redis fan-in failed: %s; retrying", exc)
            attempt += 1
            await _backoff_sleep(stop, attempt)
        finally:
            await _aclose_redis_fan_in(pubsub, client, channel)
