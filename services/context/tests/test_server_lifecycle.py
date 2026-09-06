"""gRPC server lifecycle / wiring tests (milestone 3.5.C.6)."""

from __future__ import annotations

import asyncio
import logging
import runpy
import sys
import types
from uuid import uuid4

import pytest

from app.assemble import ContextAssembler
from app.clients.directive import DirectivePayload
from app.clients.memory import MemoryHitPayload
from app.config import ContextSettings
from app.retrieval import ParallelRetriever
from app.server import (
    AssemblyRuntime,
    _is_loopback_addr,
    build_assembler_from_settings,
    build_server,
)

ORG = uuid4()
AGENT = uuid4()


def _settings(**overrides: object) -> ContextSettings:
    base: dict[str, object] = {
        "timeout_ms": 45.0,
        "deadline_ms": 40.0,
        "directive_timeout_ms": 5.0,
        "hot_timeout_ms": 15.0,
        "cold_timeout_ms": 45.0,
        "formatter_nonce_bytes": 16,
        "packer_dp_cell_ceiling": 70 * 6251,
        "packer_max_consecutive_skips": 5,
        "grpc_addr": "127.0.0.1:0",
        "memory_base_url": "",
        "memory_api_token": "",
        "redis_url": "",
    }
    base.update(overrides)
    return ContextSettings.model_construct(**base)


class _StubDirective:
    async def lookup(self, org_id, agent_id) -> DirectivePayload:
        return DirectivePayload(
            content="Be careful.",
            injection_mode="system_first",
            version_id=None,
        )


class _StubMemory:
    async def get_hot_memories(self, *_args, **_kwargs):
        return [
            MemoryHitPayload(
                memory_id=str(uuid4()),
                org_id=str(ORG),
                agent_id=str(AGENT),
                content="prefers dark mode",
                category="preference",
                confidence=0.9,
                similarity=0.8,
                rank=1,
                source="hot_cache",
            )
        ]

    async def search_memories(self, *_args, **_kwargs):
        return []


def _assembler() -> ContextAssembler:
    settings = _settings()
    return ContextAssembler(
        settings=settings,
        retriever=ParallelRetriever(
            settings=settings,
            memory=_StubMemory(),  # type: ignore[arg-type]
            directive=_StubDirective(),
        ),
    )


@pytest.mark.asyncio
async def test_build_server_uses_settings_grpc_addr() -> None:
    server, port = build_server(_assembler(), settings=_settings())
    assert isinstance(port, int)
    assert port >= 0
    assert server is not None
    await server.stop(grace=None)


def test_is_loopback_addr() -> None:
    assert _is_loopback_addr("127.0.0.1:9092")
    assert _is_loopback_addr("localhost:9092")
    assert _is_loopback_addr("[::1]:9092")
    assert not _is_loopback_addr("0.0.0.0:9092")
    assert not _is_loopback_addr("10.0.0.5:9092")


@pytest.mark.asyncio
async def test_build_server_warns_non_loopback_without_auth(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.server"):
        server, _port = build_server(_assembler(), listen_addr="0.0.0.0:0")
    assert any(
        "context_assembly_grpc_non_loopback_bind" in r.message
        and "3.5.D.1" in r.message
        and "ADR-0071" in r.message
        for r in caplog.records
    )
    await server.stop(grace=None)


def test_build_assembler_requires_memory_base_url() -> None:
    settings = _settings()
    with pytest.raises(ValueError, match="MEMORY_BASE_URL"):
        build_assembler_from_settings(settings)


def test_build_assembler_from_settings_ok() -> None:
    assembler = build_assembler_from_settings(
        _settings(memory_base_url="http://memory.test", memory_api_token="tok")
    )
    assert isinstance(assembler, ContextAssembler)


def test_build_assembler_with_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    redis_async = types.ModuleType("redis.asyncio")
    redis_async.from_url = lambda url: object()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "redis", types.ModuleType("redis"))
    monkeypatch.setitem(sys.modules, "redis.asyncio", redis_async)
    assembler = build_assembler_from_settings(
        _settings(
            memory_base_url="http://memory.test",
            memory_api_token="tok",
            redis_url="redis://localhost:6379/0",
        )
    )
    assert isinstance(assembler, ContextAssembler)


@pytest.mark.asyncio
async def test_serve_forever_starts_and_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import server as server_mod

    class _FakeMemory:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    class _FakeServer:
        def __init__(self) -> None:
            self.started = False
            self.stopped = False

        async def start(self) -> None:
            self.started = True

        async def wait_for_termination(self) -> None:
            self.stopped = True

        async def stop(self, grace: float | None = None) -> None:
            self.stopped = True

    fake = _FakeServer()
    memory = _FakeMemory()
    runtime = AssemblyRuntime(
        assembler=_assembler(),
        memory=memory,  # type: ignore[arg-type]
        redis_client=None,
    )
    monkeypatch.setattr(server_mod, "build_server", lambda *a, **k: (fake, 9092))
    monkeypatch.setattr(
        server_mod,
        "build_runtime_from_settings",
        lambda cfg: runtime,
    )
    await server_mod.serve_forever(
        _settings(memory_base_url="http://memory.test", memory_api_token="tok")
    )
    assert fake.started is True
    assert fake.stopped is True
    assert memory.closed is True


@pytest.mark.asyncio
async def test_serve_forever_signal_stops_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import server as server_mod

    class _FakeMemory:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    class _FakeRedis:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    class _FakeServer:
        def __init__(self) -> None:
            self.stop_grace: float | None = None
            self._term = asyncio.Event()

        async def start(self) -> None:
            return None

        async def wait_for_termination(self) -> None:
            await self._term.wait()

        async def stop(self, grace: float | None = None) -> None:
            self.stop_grace = grace
            self._term.set()

    fake = _FakeServer()
    memory = _FakeMemory()
    redis = _FakeRedis()
    runtime = AssemblyRuntime(
        assembler=_assembler(),
        memory=memory,  # type: ignore[arg-type]
        redis_client=redis,
    )
    monkeypatch.setattr(server_mod, "build_server", lambda *a, **k: (fake, 9092))
    monkeypatch.setattr(
        server_mod,
        "build_runtime_from_settings",
        lambda cfg: runtime,
    )

    shutdown_box: list[asyncio.Event] = []
    real_event = asyncio.Event

    def _tracking_event() -> asyncio.Event:
        ev = real_event()
        shutdown_box.append(ev)
        return ev

    monkeypatch.setattr(server_mod.asyncio, "Event", _tracking_event)
    serve_task = asyncio.create_task(
        server_mod.serve_forever(
            _settings(memory_base_url="http://memory.test", memory_api_token="tok")
        )
    )
    await asyncio.sleep(0.05)
    assert shutdown_box, "serve_forever should create a shutdown Event"
    shutdown_box[0].set()
    await serve_task
    assert fake.stop_grace == server_mod._SHUTDOWN_GRACE_S
    assert memory.closed is True
    assert redis.closed is True


@pytest.mark.asyncio
async def test_serve_forever_cancel_stops_before_aclose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If cancelled after start(), stop the server before closing clients."""
    from app import server as server_mod

    order: list[str] = []

    class _FakeMemory:
        async def aclose(self) -> None:
            order.append("aclose")

    class _FakeServer:
        def __init__(self) -> None:
            self._hang = asyncio.Event()

        async def start(self) -> None:
            order.append("start")

        async def wait_for_termination(self) -> None:
            await self._hang.wait()

        async def stop(self, grace: float | None = None) -> None:
            del grace
            order.append("stop")
            self._hang.set()

    runtime = AssemblyRuntime(
        assembler=_assembler(),
        memory=_FakeMemory(),  # type: ignore[arg-type]
        redis_client=None,
    )
    monkeypatch.setattr(
        server_mod, "build_server", lambda *a, **k: (_FakeServer(), 9092)
    )
    monkeypatch.setattr(
        server_mod,
        "build_runtime_from_settings",
        lambda cfg: runtime,
    )

    serve_task = asyncio.create_task(
        server_mod.serve_forever(
            _settings(memory_base_url="http://memory.test", memory_api_token="tok")
        )
    )
    for _ in range(50):
        if "start" in order:
            break
        await asyncio.sleep(0.01)
    assert "start" in order
    serve_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await serve_task
    assert order.index("stop") < order.index("aclose")


def test_main_invokes_serve_forever(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import server as server_mod

    called: list[bool] = []

    async def _fake_serve(settings=None):  # type: ignore[no-untyped-def]
        called.append(True)

    monkeypatch.setattr(server_mod, "serve_forever", _fake_serve)
    monkeypatch.setattr(server_mod.logging, "basicConfig", lambda **_: None)
    server_mod.main()
    assert called == [True]


def test_dunder_main_module(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[bool] = []

    def _fake_main() -> None:
        called.append(True)

    sys.modules.pop("app.__main__", None)
    monkeypatch.setattr("app.server.main", _fake_main)
    runpy.run_module("app.__main__", run_name="__main__")
    assert called == [True]
