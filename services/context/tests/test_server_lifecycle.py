"""gRPC server lifecycle / wiring tests (milestone 3.5.C.6 / ADR-0096)."""

from __future__ import annotations

import asyncio
import runpy
import sys
import types

import grpc
import pytest
from pydantic import SecretStr
from server_test_support import SERVICE_TOKEN
from server_test_support import assembler as _assembler
from server_test_support import settings as _settings

from app.assemble import ContextAssembler
from app.server import (
    AssemblyRuntime,
    _is_loopback_addr,
    _require_loopback_bind,
    _require_unary,
    build_assembler_from_settings,
    build_server,
)


@pytest.mark.asyncio
async def test_build_server_uses_settings_grpc_addr() -> None:
    server, port = build_server(_assembler(), settings=_settings())
    assert isinstance(port, int)
    assert port >= 0
    assert server is not None
    await server.stop(grace=None)


def test_is_loopback_addr() -> None:
    """Literal IPs only; ``localhost`` is a name and must be resolved."""
    assert _is_loopback_addr("127.0.0.1:9092")
    assert _is_loopback_addr("[::1]:9092")
    assert not _is_loopback_addr("localhost:9092")
    assert not _is_loopback_addr("0.0.0.0:9092")
    assert not _is_loopback_addr("10.0.0.5:9092")


def test_require_loopback_bind_accepts_localhost_that_resolves_to_loopback() -> None:
    _require_loopback_bind("localhost:9092")


@pytest.mark.parametrize(
    "addr",
    ["0.0.0.0:0", "10.0.0.5:0", "[::]:0"],
)
def test_build_server_refuses_non_loopback_bind(addr: str) -> None:
    """ADR-0096: the service is loopback-only, so an exposed bind is fatal."""
    with pytest.raises(ValueError, match="loopback"):
        build_server(_assembler(), listen_addr=addr, settings=_settings())


def test_build_server_refuses_name_resolving_off_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import server as server_mod

    def _fake_getaddrinfo(*_args, **_kwargs):
        return [(2, 1, 6, "", ("10.0.0.5", 0))]

    monkeypatch.setattr(server_mod.socket, "getaddrinfo", _fake_getaddrinfo)
    with pytest.raises(ValueError, match="loopback"):
        build_server(_assembler(), listen_addr="context.internal:0", settings=_settings())


def test_build_server_refuses_unresolvable_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import server as server_mod

    def _fail(*_args, **_kwargs):
        raise server_mod.socket.gaierror("no such host")

    monkeypatch.setattr(server_mod.socket, "getaddrinfo", _fail)
    with pytest.raises(ValueError, match="loopback"):
        build_server(_assembler(), listen_addr="missing.invalid:0", settings=_settings())


@pytest.mark.parametrize(
    "addr",
    [
        "",
        "::1:0",
        "127.0.0.1",
        "127.0.0.1:abc",
        "127.0.0.1:٩٠٩٢",
        "127.0.0.1:70000",
        " 127.0.0.1:9092",
        "127.0.0.1:9092 ",
        "[::1:9092",
    ],
)
def test_require_loopback_bind_rejects_malformed_addresses(addr: str) -> None:
    from app import server as server_mod

    with pytest.raises(ValueError):
        server_mod._require_loopback_bind(addr)


def test_require_loopback_bind_accepts_name_resolving_to_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import server as server_mod

    def _fake_getaddrinfo(*_args, **_kwargs):
        return [
            (2, 1, 6, "", ("127.0.0.1", 0)),
            (10, 1, 6, "", ("::1", 0, 0, 0)),
        ]

    monkeypatch.setattr(server_mod.socket, "getaddrinfo", _fake_getaddrinfo)
    server_mod._require_loopback_bind("context.internal:9092")


def test_require_loopback_bind_refuses_when_any_address_is_public(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import server as server_mod

    def _mixed_getaddrinfo(*_args, **_kwargs):
        return [
            (2, 1, 6, "", ("127.0.0.1", 0)),
            (2, 1, 6, "", ("203.0.113.7", 0)),
        ]

    monkeypatch.setattr(server_mod.socket, "getaddrinfo", _mixed_getaddrinfo)
    with pytest.raises(ValueError, match="loopback"):
        server_mod._require_loopback_bind("context.internal:9092")


def test_require_loopback_bind_requires_a_host() -> None:
    from app import server as server_mod

    with pytest.raises(ValueError, match="host:port"):
        server_mod._require_loopback_bind(":9092")


@pytest.mark.parametrize("value", ["not-an-ip", "127.0.0.1.example", ""])
def test_is_loopback_ip_rejects_non_addresses(value: str) -> None:
    from app import server as server_mod

    assert server_mod._is_loopback_ip(value) is False


def test_is_loopback_ip_accepts_ipv6_scope_suffix() -> None:
    from app import server as server_mod

    assert server_mod._is_loopback_ip("::1%lo") is True


def test_build_server_requires_a_service_token() -> None:
    with pytest.raises(ValueError, match="IBEX_CONTEXT_GRPC_SERVICE_TOKEN"):
        build_server(
            _assembler(),
            listen_addr="127.0.0.1:0",
            settings=_settings(grpc_service_token=SecretStr("")),
        )


def test_build_server_rejects_short_service_token() -> None:
    with pytest.raises(ValueError, match="IBEX_CONTEXT_GRPC_SERVICE_TOKEN"):
        build_server(
            _assembler(),
            listen_addr="127.0.0.1:0",
            settings=_settings(grpc_service_token=SecretStr("too-short")),
        )


def test_build_server_rejects_memory_token_reuse() -> None:
    """Reusing the memory credential would let one leak compromise both hops."""
    with pytest.raises(ValueError, match="must differ"):
        build_server(
            _assembler(),
            listen_addr="127.0.0.1:0",
            settings=_settings(
                grpc_service_token=SecretStr(SERVICE_TOKEN),
                memory_api_token=SecretStr(SERVICE_TOKEN),
            ),
        )


def test_require_unary_rejects_streaming_handler() -> None:
    handler = grpc.stream_stream_rpc_method_handler(lambda request, context: None)
    with pytest.raises(ValueError, match="unary"):
        _require_unary("AssembleContext", handler)


def test_server_disables_port_reuse() -> None:
    """H3: a same-UID process must not be able to share (and sniff) the port."""
    from app import server as server_mod

    assert ("grpc.so_reuseport", 0) in server_mod._SERVER_OPTIONS


def test_require_unary_accepts_unary_handler() -> None:
    handler = grpc.unary_unary_rpc_method_handler(lambda request, context: None)
    _require_unary("AssembleContext", handler)


def test_build_assembler_requires_memory_base_url() -> None:
    cfg = _settings()
    with pytest.raises(ValueError, match="MEMORY_BASE_URL"):
        build_assembler_from_settings(cfg)


def test_build_assembler_from_settings_ok() -> None:
    result = build_assembler_from_settings(
        _settings(
            memory_base_url="http://memory.test",
            memory_api_token=SecretStr("tok"),
        )
    )
    assert isinstance(result, ContextAssembler)


def test_build_assembler_with_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    redis_async = types.ModuleType("redis.asyncio")
    redis_async.from_url = lambda url: object()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "redis", types.ModuleType("redis"))
    monkeypatch.setitem(sys.modules, "redis.asyncio", redis_async)
    result = build_assembler_from_settings(
        _settings(
            memory_base_url="http://memory.test",
            memory_api_token=SecretStr("tok"),
            redis_url="redis://localhost:6379/0",
        )
    )
    assert isinstance(result, ContextAssembler)


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
    await server_mod.serve_forever(_settings())
    assert fake.started is True
    assert fake.stopped is True
    assert memory.closed is True


@pytest.mark.asyncio
async def test_serve_forever_refuses_without_service_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Startup refusal is real: the runtime is closed and no port is bound."""
    from app import server as server_mod

    closed: list[bool] = []

    class _FakeMemory:
        async def aclose(self) -> None:
            closed.append(True)

    runtime = AssemblyRuntime(
        assembler=_assembler(),
        memory=_FakeMemory(),  # type: ignore[arg-type]
        redis_client=None,
    )
    monkeypatch.setattr(
        server_mod,
        "build_runtime_from_settings",
        lambda cfg: runtime,
    )
    with pytest.raises(ValueError, match="IBEX_CONTEXT_GRPC_SERVICE_TOKEN"):
        await server_mod.serve_forever(
            _settings(grpc_service_token=SecretStr(""), grpc_addr="127.0.0.1:0")
        )
    assert closed == [True]


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
    serve_task = asyncio.create_task(server_mod.serve_forever(_settings()))
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

    serve_task = asyncio.create_task(server_mod.serve_forever(_settings()))
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
